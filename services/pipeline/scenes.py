from __future__ import annotations

import logging
import math
from pathlib import Path

from pipeline.media import grab_frame
from pipeline.types import Keyframe

log = logging.getLogger("videomind.scenes")


def detect_scene_spans(video_path: str | Path) -> list[tuple[float, float]]:
    from scenedetect import AdaptiveDetector, detect

    try:
        scenes = detect(str(video_path), AdaptiveDetector())
    except Exception:
        log.exception("PySceneDetect failed for %s", video_path)
        return []
    spans: list[tuple[float, float]] = []
    for start, end in scenes:
        spans.append((_seconds(start), _seconds(end)))
    return spans


def _seconds(timecode) -> float:
    seconds = getattr(timecode, "seconds", None)
    if seconds is not None:
        return float(seconds)
    return float(timecode.get_seconds())


def keyframe_times(
    spans: list[tuple[float, float]],
    duration: float,
    every: float = 30.0,
) -> list[float]:
    """Middle of each scene, plus a frame in any 30s bucket the scenes missed."""
    if duration <= 0:
        return []
    mids: list[float] = []
    for start, end in spans:
        mid = (start + end) / 2
        if 0 <= mid <= duration:
            mids.append(mid)
    if not mids:
        mids.append(min(duration / 2, duration))
    buckets = max(1, math.ceil(duration / every)) if every > 0 else 1
    extra: list[float] = []
    if every > 0:
        for index in range(buckets):
            left = index * every
            right = min(duration, (index + 1) * every)
            if right <= left:
                continue

            def covered(ts: float, lo: float = left, hi: float = right, i: int = index) -> bool:
                if lo <= ts < hi:
                    return True
                return i == buckets - 1 and abs(ts - duration) < 1e-3

            if not any(covered(ts) for ts in mids):
                extra.append(min(duration, (left + right) / 2))
    times = sorted({round(ts, 3) for ts in [*mids, *extra]})
    return [ts for ts in times if 0 <= ts <= duration]


def drop_similar(items: list[tuple[float, object]], threshold: int) -> list[tuple[float, object]]:
    """Drop a frame when its perceptual hash is close to the previous kept frame."""
    kept: list[tuple[float, object]] = []
    for item in items:
        if kept and (item[1] - kept[-1][1]) <= threshold:
            continue
        kept.append(item)
    return kept


def _phash(path: Path):
    import imagehash
    from PIL import Image

    with Image.open(path) as image:
        return imagehash.phash(image)


def _thumbnail(source: Path, dest: Path) -> None:
    from PIL import Image

    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((320, 320))
        image.save(dest, "JPEG", quality=80)


def extract_keyframes(
    video_path: str | Path,
    duration: float,
    *,
    work_dir: Path,
    every: float = 30.0,
    phash_threshold: int = 6,
    video_id: str = "video",
) -> list[Keyframe]:
    video_path = Path(video_path)
    spans = detect_scene_spans(video_path)
    if not spans:
        spans = [(0.0, duration)]
    times = keyframe_times(spans, duration, every=every)
    work_dir.mkdir(parents=True, exist_ok=True)
    hashed: list[tuple[float, object, Path]] = []
    for ts in times:
        frame_path = work_dir / f"frame_{ts:.3f}.jpg"
        try:
            grab_frame(video_path, ts, frame_path)
            hashed.append((ts, _phash(frame_path), frame_path))
        except Exception:
            log.exception("failed to grab frame at %.3f", ts)
    kept_pairs = drop_similar([(ts, digest) for ts, digest, _ in hashed], phash_threshold)
    kept_times = {ts for ts, _ in kept_pairs}
    frames: list[Keyframe] = []
    for ts, digest, frame_path in hashed:
        if ts not in kept_times:
            frame_path.unlink(missing_ok=True)
            continue
        thumb = work_dir / f"thumb_{ts:.3f}.jpg"
        _thumbnail(frame_path, thumb)
        stamp = f"{ts:.3f}"
        frames.append(
            Keyframe(
                time=ts,
                image_path=str(frame_path),
                thumb_path=str(thumb),
                image_hash=str(digest),
                image_key=f"videos/{video_id}/keyframes/{stamp}.jpg",
                thumb_key=f"videos/{video_id}/thumbs/{stamp}.jpg",
            )
        )
    log.info(
        "scenes=%d candidate_frames=%d kept_frames=%d duration=%.2f",
        len(spans),
        len(times),
        len(frames),
        duration,
    )
    return frames
