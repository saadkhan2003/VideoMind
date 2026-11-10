from __future__ import annotations

from pipeline.types import AsrSegment, Chunk, Keyframe


def chunk_transcript(
    sentences: list[AsrSegment],
    duration: float,
    window: float = 45.0,
    overlap: float = 10.0,
    max_len: float = 60.0,
) -> list[Chunk]:
    """Build overlapping time windows snapped to sentence boundaries.

    Coverage starts at 0 and ends at ``duration``. No window is longer than
    ``max_len``. Consecutive windows overlap by about ``overlap`` seconds when
    sentence boundaries allow it. The tail window always closes at ``duration``
    when the remainder fits in ``max_len``.
    """
    if duration <= 0:
        return []
    if window <= 0 or overlap < 0 or overlap >= window:
        raise ValueError("window must be greater than overlap, and overlap must be >= 0")
    if max_len < window:
        max_len = window
    if not sentences:
        return _fixed_windows(duration, window, overlap, max_len)

    chunks: list[Chunk] = []
    start = 0.0
    for _ in range(10000):
        if start >= duration - 1e-3:
            break
        remaining = duration - start
        if remaining <= max_len + 1e-9:
            end = duration
        else:
            target = start + window
            latest = start + max_len
            candidates = [s.end for s in sentences if start + 1e-6 < s.end <= latest + 1e-6]
            if not candidates:
                end = min(duration, start + window)
            else:
                end = min(candidates, key=lambda value: (abs(value - target), value))
            if end <= start:
                end = min(duration, start + window)
        text = " ".join(
            s.text.strip()
            for s in sentences
            if s.text and s.end > start + 1e-6 and s.start < end - 1e-6
        ).strip()
        chunks.append(Chunk(start=start, end=end, transcript_text=text))
        if end >= duration - 1e-3:
            break
        desired = end - overlap
        starts = [s.start for s in sentences if start + 1e-3 < s.start < end - 1e-6]
        if starts:
            next_start = min(starts, key=lambda value: (abs(value - desired), value))
        else:
            next_start = desired
        if next_start <= start:
            next_start = min(end - 1e-3, start + max(0.5, (end - start) - overlap))
        if next_start >= end:
            next_start = max(start + 0.25, end - min(overlap, (end - start) / 2))
        if next_start <= start:
            next_start = min(duration, start + 0.5)
        start = next_start
    return chunks


def _fixed_windows(duration: float, window: float, overlap: float, max_len: float) -> list[Chunk]:
    chunks: list[Chunk] = []
    start = 0.0
    step_guard = 0
    while start < duration - 1e-3 and step_guard < 10000:
        step_guard += 1
        end = min(duration, start + min(window, max_len))
        chunks.append(Chunk(start=start, end=end, transcript_text=""))
        if end >= duration - 1e-3:
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start
    return chunks


def attach_visuals(chunks: list[Chunk], keyframes: list[Keyframe]) -> list[Chunk]:
    if not chunks:
        return chunks
    last_index = len(chunks) - 1
    for index, chunk in enumerate(chunks):
        inside = []
        for frame in keyframes:
            if index == last_index:
                keep = chunk.start - 1e-6 <= frame.time <= chunk.end + 1e-6
            else:
                keep = chunk.start - 1e-6 <= frame.time < chunk.end - 1e-6
            if keep:
                inside.append(frame)
        chunk.visual_caption = " ".join(frame.caption for frame in inside if frame.caption).strip()
        chunk.ocr_text = " ".join(frame.ocr_text for frame in inside if frame.ocr_text).strip()
        if inside:
            mid = (chunk.start + chunk.end) / 2
            best = min(inside, key=lambda frame: abs(frame.time - mid))
            chunk.keyframe_key = best.thumb_key or best.image_key
            chunk.keyframe_time = best.time
    return chunks
