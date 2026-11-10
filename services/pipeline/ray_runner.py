"""Ray DAG for one video.

ASR and scene detection are separate tasks so they run at the same time.
Captioning is its own task (GPU queue in a real cluster). Chunk, embed, and
upsert run after both branches finish. Requires a shared Qdrant URL and a
database both the driver and the workers can reach — embedded Qdrant and
SQLite are single-process. If Ray is not installed, callers should use the
poll worker.
"""

from __future__ import annotations

import logging

log = logging.getLogger("videomind.ray")

DAG = (
    "extract_audio",
    "asr",
    "scenes",
    "captions",
    "chunk",
    "embed",
    "upsert",
)


def ray_available() -> bool:
    try:
        import ray  # noqa: F401
    except ImportError:
        return False
    return True


def _ensure_ray() -> None:
    import ray

    if not ray.is_initialized():
        ray.init(ignore_reinit_error=True, include_dashboard=False, log_to_driver=False)


def _ingest_remote():
    import ray

    cached = getattr(_ingest_remote, "task", None)
    if cached is None:
        cached = ray.remote(max_retries=2)(_ingest_body)
        _ingest_remote.task = cached
    return cached


def submit(video_id: str, settings) -> str:
    """Enqueue the ingestion DAG. Returns the ObjectRef hex, if Ray is installed."""
    if not ray_available():
        raise RuntimeError("Ray is not installed. Set WORKER_BACKEND=poll or pip install ray.")
    if not settings.qdrant_url:
        raise RuntimeError(
            "Ray workers need QDRANT_URL pointing at a Qdrant server. "
            "The embedded store cannot be shared across processes."
        )
    _ensure_ray()
    ref = _ingest_remote().options(num_cpus=0.1).remote(video_id, settings.model_dump())
    return ref.hex()


def run_blocking(video_id: str, settings) -> dict:
    import ray

    _ensure_ray()
    if not settings.qdrant_url:
        raise RuntimeError("QDRANT_URL is required for the Ray backend")
    ref = _ingest_remote().remote(video_id, settings.model_dump())
    return ray.get(ref)


def _remote_asr(wav_path: str, model: str, device: str, compute: str):
    from pipeline.asr import transcribe_file

    return transcribe_file(
        wav_path,
        model_size=model,
        device=device,
        compute_type=compute,
        vad_filter=True,
    )


def _remote_scenes(video_path: str, duration: float, work_dir: str, every: float, threshold: int, video_id: str):
    from pathlib import Path

    from pipeline.scenes import extract_keyframes

    return extract_keyframes(
        video_path,
        duration,
        work_dir=Path(work_dir),
        every=every,
        phash_threshold=threshold,
        video_id=video_id,
    )


def parallel_asr_and_scenes(video_path, wav_path, duration, settings, work_dir, video_id):
    """Run the two branches with Ray when it is installed, else threads.

    Returned to the caller so a unit test can execute the thread fallback
    without a cluster. The Ray branch is what `submit` uses inside `_ingest`.
    """
    if ray_available() and settings.worker_backend == "ray":
        import ray

        _ensure_ray()
        asr_remote = ray.remote(num_cpus=1)(_remote_asr)
        scene_remote = ray.remote(num_cpus=1)(_remote_scenes)
        return ray.get(
            [
                asr_remote.remote(
                    wav_path,
                    settings.whisper_model,
                    settings.whisper_device,
                    settings.whisper_compute_type,
                ),
                scene_remote.remote(
                    video_path,
                    duration,
                    work_dir,
                    settings.keyframe_every_s,
                    settings.phash_threshold,
                    video_id,
                ),
            ]
        )
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        asr_f = pool.submit(
            _remote_asr,
            wav_path,
            settings.whisper_model,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        scene_f = pool.submit(
            _remote_scenes,
            video_path,
            duration,
            work_dir,
            settings.keyframe_every_s,
            settings.phash_threshold,
            video_id,
        )
        return asr_f.result(), scene_f.result()


def _ingest_body(video_id: str, settings_dict: dict) -> dict:
    from pipeline.config import Settings
    from pipeline.orchestrator import run_pipeline
    from pipeline.runtime import Resources

    settings = Settings(**settings_dict)
    resources = Resources(settings)
    try:
        return run_pipeline(
            video_id,
            settings,
            repo=resources.repo,
            store=resources.store,
            index=resources.index,
        )
    finally:
        resources.close()


