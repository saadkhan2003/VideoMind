import pytest

from pipeline.chunker import attach_visuals, chunk_transcript
from pipeline.types import AsrSegment, Keyframe


def _sentences(duration: float, step: float = 10.0) -> list[AsrSegment]:
    sentences = []
    t = 0.0
    index = 0
    while t < duration - 1e-6:
        end = min(duration, t + step)
        sentences.append(AsrSegment(t, end, f"sentence {index}"))
        index += 1
        t = end
    return sentences


def test_hand_computed_windows_snap_to_sentences():
    duration = 100.0
    chunks = chunk_transcript(_sentences(duration), duration, window=45, overlap=10, max_len=60)
    assert [(c.start, c.end) for c in chunks] == [(0.0, 40.0), (30.0, 70.0), (60.0, 100.0)]
    for chunk in chunks:
        assert chunk.end - chunk.start <= 60
    for left, right in zip(chunks, chunks[1:]):
        assert right.start < left.end
        assert left.end - right.start == pytest.approx(10)


def test_fixed_windows_when_there_are_no_sentences():
    chunks = chunk_transcript([], 100, window=45, overlap=10, max_len=60)
    assert [(c.start, c.end) for c in chunks] == [(0.0, 45.0), (35.0, 80.0), (70.0, 100.0)]
    cursor = 0.0
    for chunk in chunks:
        assert chunk.start <= cursor + 1e-6
        cursor = max(cursor, chunk.end)
        assert chunk.end - chunk.start <= 60
    assert cursor == pytest.approx(100)


def test_no_gaps_and_max_length_on_uneven_sentences():
    sentences = [
        AsrSegment(0, 4, "a"),
        AsrSegment(4, 9, "b"),
        AsrSegment(9, 22, "c"),
        AsrSegment(22, 30, "d"),
        AsrSegment(30, 48, "e"),
        AsrSegment(48, 70, "f"),
        AsrSegment(70, 91, "g"),
        AsrSegment(91, 100, "h"),
    ]
    chunks = chunk_transcript(sentences, 100, window=45, overlap=10, max_len=60)
    assert chunks[0].start == 0
    assert chunks[-1].end == pytest.approx(100)
    covered = 0.0
    for chunk in chunks:
        assert chunk.start <= covered + 1e-6
        assert chunk.end - chunk.start <= 60 + 1e-6
        covered = max(covered, chunk.end)
    assert covered == pytest.approx(100)
    for left, right in zip(chunks, chunks[1:]):
        assert right.start > left.start
        assert right.start <= left.end + 1e-6


def test_segment_text_stays_inside_the_window():
    sentences = [
        AsrSegment(0, 10, "alpha"),
        AsrSegment(10, 20, "beta"),
        AsrSegment(20, 30, "gamma"),
    ]
    chunks = chunk_transcript(sentences, 30, window=15, overlap=5, max_len=20)
    assert chunks
    assert "alpha" in chunks[0].transcript_text
    assert "gamma" not in chunks[0].transcript_text or chunks[0].end > 20


def test_attach_visuals_uses_frames_inside_the_window():
    chunks = chunk_transcript(
        [AsrSegment(0, 10, "a"), AsrSegment(10, 20, "b")],
        20,
        window=10,
        overlap=2,
        max_len=12,
    )
    frames = [
        Keyframe(
            time=5,
            image_path="",
            thumb_path="",
            image_hash="a",
            thumb_key="k1",
            caption="diagram",
            ocr_text="FIG",
        ),
        Keyframe(
            time=15,
            image_path="",
            thumb_path="",
            image_hash="b",
            thumb_key="k2",
            caption="chart",
            ocr_text="BAR",
        ),
    ]
    attach_visuals(chunks, frames)
    owners = {frame_key: chunk for chunk in chunks for frame_key in [chunk.keyframe_key] if frame_key}
    assert any(chunk.ocr_text == "FIG" or "FIG" in chunk.ocr_text for chunk in chunks)
    assert any("BAR" in chunk.ocr_text for chunk in chunks)
    assert owners


def test_rejects_overlap_that_is_not_smaller_than_the_window():
    with pytest.raises(ValueError):
        chunk_transcript([], 10, window=5, overlap=5, max_len=8)
