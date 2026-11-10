from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipeline.asr import transcribe_file
from pipeline.budget import UsdBudget
from pipeline.captions import CachingCaptioner, build_captioner, caption_keyframes
from pipeline.chunker import attach_visuals, chunk_transcript
from pipeline.config import Settings
from pipeline.embed import build_embedder
from pipeline.index import SegmentIndex, point_id
from pipeline.media import extract_audio, probe_duration
from pipeline.metrics import JOB_FAILURES, STAGE_DURATION
from pipeline.repository import Repository
from pipeline.scenes import extract_keyframes
from pipeline.sparse import sparse_vector
from pipeline.storage import LocalStore, S3Store
from pipeline.tracing import Tracer
from pipeline.types import Chunk, Keyframe, Transcript

log = logging.getLogger("videomind.pipeline")


def run_with_retry(fn, attempts: int = 3, base_delay: float = 0.2, on_attempt=None):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if on_attempt:
                on_attempt(attempt, "running", "")
            result = fn()
            if on_attempt:
                on_attempt(attempt, "succeeded", "")
            return result
        except Exception as exc:
            last_error = exc
            if on_attempt:
                on_attempt(attempt, "failed", str(exc))
            if attempt == attempts:
                raise
            time.sleep(base_delay * (2 ** (attempt - 1)))
    if last_error:
        raise last_error
    raise RuntimeError("retry failed without an exception")


def run_pipeline(
    video_id: str,
    settings: Settings,
    *,
    repo: Repository,
    store: LocalStore | S3Store,
    index: SegmentIndex,
    hooks: dict | None = None,
    already_processing: bool = False,
) -> dict:
    hooks = hooks or {}
    tracer = Tracer(settings)
    video = repo.get_video(video_id)
    if video is None:
        raise KeyError(video_id)
    job = repo.latest_job(video_id)
    if job is None:
        raise KeyError(f"no job for {video_id}")
    if job["status"] == "queued":
        repo.transition(job["id"], "processing")
    elif job["status"] != "processing":
        repo.transition(job["id"], "queued")
        repo.transition(job["id"], "processing")
    elif not already_processing and job["status"] == "processing":
        pass

    work = Path(settings.data_dir) / "work" / video_id
    work.mkdir(parents=True, exist_ok=True)
    try:
        source = store.materialize(video["object_key"], work / Path(video["filename"]).name)
        duration = _stage(
            repo,
            job["id"],
            "extract_audio",
            settings,
            lambda: _extract(source, work / "audio.wav", store, video_id, repo),
        )
        wav = work / "audio.wav"

        def do_asr() -> Transcript:
            if "transcribe" in hooks:
                return hooks["transcribe"](str(wav), settings)
            return transcribe_file(
                wav,
                model_size=settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
                vad_filter=True,
            )

        def do_scenes() -> list[Keyframe]:
            if "keyframes" in hooks:
                return hooks["keyframes"](str(source), duration, settings)
            return extract_keyframes(
                source,
                duration,
                work_dir=work / "frames",
                every=settings.keyframe_every_s,
                phash_threshold=settings.phash_threshold,
                video_id=video_id,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            asr_future = pool.submit(
                lambda: _stage(repo, job["id"], "asr", settings, do_asr)
            )
            scene_future = pool.submit(
                lambda: _stage(repo, job["id"], "scenes", settings, do_scenes)
            )
            transcript = asr_future.result()
            frames = scene_future.result()

        store.put_bytes(
            f"videos/{video_id}/transcript.json",
            json.dumps(transcript.to_dict()).encode(),
            "application/json",
        )
        repo.update_video(video_id, language=transcript.language, duration_s=duration)
        for frame in frames:
            if frame.image_path and Path(frame.image_path).exists():
                store.put_file(frame.image_key, Path(frame.image_path), "image/jpeg")
            if frame.thumb_path and Path(frame.thumb_path).exists():
                store.put_file(frame.thumb_key, Path(frame.thumb_path), "image/jpeg")

        def do_captions() -> list[Keyframe]:
            if "caption" in hooks:
                for frame in frames:
                    result = hooks["caption"](frame.image_path, frame.time, settings)
                    frame.caption = result.description
                    frame.ocr_text = result.ocr_text
                    frame.caption_backend = result.backend
                    frame.caption_model = result.model
                return frames
            budget = None
            if settings.caption_backend == "openrouter":
                budget = UsdBudget(settings.caption_budget_usd)
            captioner = CachingCaptioner(
                build_captioner(settings), settings, tracer, budget=budget
            )
            return caption_keyframes(frames, captioner)

        frames = _stage(repo, job["id"], "captions", settings, do_captions)

        def do_chunk() -> list[Chunk]:
            chunks = chunk_transcript(
                transcript.segments,
                duration or transcript.duration,
                window=settings.chunk_window_s,
                overlap=settings.chunk_overlap_s,
                max_len=settings.chunk_max_s,
            )
            log.info("video=%s segments=%d", video_id, len(chunks))
            return attach_visuals(chunks, frames)

        chunks = _stage(repo, job["id"], "chunk", settings, do_chunk)
        embedder = hooks.get("embedder") or build_embedder(
            settings.embedding_backend, settings.embedding_model, settings.embedding_dim
        )

        def do_embed():
            texts = [c.transcript_text for c in chunks]
            visuals = [f"{c.visual_caption} {c.ocr_text}".strip() for c in chunks]
            return embedder.embed(texts), embedder.embed(visuals)

        text_vecs, visual_vecs = _stage(repo, job["id"], "embed", settings, do_embed)

        def do_upsert():
            _upsert(index, repo, video, chunks, text_vecs, visual_vecs, transcript.language)

        _stage(repo, job["id"], "upsert", settings, do_upsert)
        repo.transition(job["id"], "indexed")
        return repo.get_job(job["id"])
    except Exception as exc:
        log.exception("pipeline failed for %s", video_id)
        JOB_FAILURES.inc()
        try:
            current = repo.get_job(job["id"])
            if current and current["status"] == "processing":
                repo.transition(job["id"], "failed", error=str(exc)[:2000])
        except Exception:
            log.exception("could not mark job failed")
        raise


def _extract(source: Path, wav: Path, store, video_id: str, repo: Repository) -> float:
    extract_audio(source, wav)
    store.put_file(f"videos/{video_id}/audio.wav", wav, "audio/wav")
    duration = probe_duration(source)
    repo.update_video(video_id, duration_s=duration)
    return duration


def _stage(repo: Repository, job_id: str, name: str, settings: Settings, fn):
    def on_attempt(attempt: int, status: str, detail: str) -> None:
        repo.update_stage(job_id, name, status if status != "running" else "running", detail)
        if status == "failed":
            log.warning("stage %s attempt %d failed: %s", name, attempt, detail)

    started = time.perf_counter()
    try:
        result = run_with_retry(
            fn,
            attempts=settings.retry_attempts,
            base_delay=settings.retry_base_delay_s,
            on_attempt=on_attempt,
        )
    except Exception:
        STAGE_DURATION.labels(stage=name).observe(time.perf_counter() - started)
        raise
    elapsed = time.perf_counter() - started
    STAGE_DURATION.labels(stage=name).observe(elapsed)
    log.info("stage %s finished in %.2fs", name, elapsed)
    return result


def _upsert(index, repo, video, chunks, text_vecs, visual_vecs, language: str) -> None:
    index.delete_video(video["id"])
    points = []
    rows = []
    for chunk, text_vec, visual_vec in zip(chunks, text_vecs, visual_vecs, strict=True):
        pid = point_id(video["id"], chunk.start)
        sparse_text = " ".join(
            part
            for part in (chunk.transcript_text, chunk.visual_caption, chunk.ocr_text)
            if part
        )
        indices, values = sparse_vector(sparse_text)
        thumb = f"/keyframes/{pid}" if chunk.keyframe_key else ""
        payload = {
            "segment_id": pid,
            "video_id": video["id"],
            "title": video["title"],
            "start_s": chunk.start,
            "end_s": chunk.end,
            "transcript_text": chunk.transcript_text,
            "visual_caption": chunk.visual_caption,
            "ocr_text": chunk.ocr_text,
            "keyframe_url": thumb,
            "lang": language or "",
        }
        points.append(
            {
                "id": pid,
                "text_dense": text_vec,
                "visual_dense": visual_vec,
                "sparse_indices": indices,
                "sparse_values": values,
                "payload": payload,
            }
        )
        rows.append(
            {
                "id": pid,
                "video_id": video["id"],
                "start_s": chunk.start,
                "end_s": chunk.end,
                "transcript_text": chunk.transcript_text,
                "visual_caption": chunk.visual_caption,
                "ocr_text": chunk.ocr_text,
                "keyframe_key": chunk.keyframe_key,
                "lang": language or "",
                "point_id": pid,
            }
        )
    index.upsert(points)
    repo.replace_segments(video["id"], rows)
    log.info("indexed video=%s points=%d collection_count=%d", video["id"], len(points), index.count())
