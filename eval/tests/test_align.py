import json
from pathlib import Path

import pytest

from eval.align_labels import align_query, find_phrase_spans
from eval.schema import load_jsonl


def _words(*triples):
    return [(token, start, end) for token, start, end in triples]


def test_repeated_phrase_is_graded_and_close_hits_merge():
    words = _words(
        ("experiment", 6.23, 6.71),
        ("on", 6.71, 7.43),
        ("experiment", 9.27, 9.77),
        ("experiment", 85.97, 86.43),
    )
    spans = find_phrase_spans(words, "experiment", grade=2, demote_repeats=True)
    assert spans[0] == [6.23, 9.77, 2]
    assert spans[1] == [85.97, 86.43, 1]


def test_caption_match_replaces_the_frame_fallback():
    spec = {
        "query_id": "hufsky-freiheit",
        "query": "banner that reads Freiheit",
        "type": "visual",
        "video_id": "hufsky-data-retention",
        "split": "test",
        "phrases": ["freiheit"],
        "grade": 2,
        "fallback_spans": [[12, 18, 2]],
    }
    segments = [
        {
            "video_id": "hufsky-data-retention",
            "start_s": 10.0,
            "end_s": 20.0,
            "visual_caption": "A banner reads Freiheit stirbt mit Sicherheit.",
            "ocr_text": "",
            "transcript_text": "",
        }
    ]
    record, warning = align_query(spec, transcripts={}, segments=segments)
    assert warning == ""
    assert record["label_source"] == "caption"
    assert record["relevant_spans"] == [[10.0, 20.0, 2]]


def test_missing_caption_keeps_the_frame_span():
    spec = {
        "query_id": "hufsky-demokratie",
        "query": "Demokratie braucht Anonymität",
        "type": "visual",
        "video_id": "hufsky-data-retention",
        "split": "test",
        "phrases": ["anonymität"],
        "grade": 2,
        "fallback_spans": [[26.2, 29.8, 2]],
    }
    segments = [
        {
            "video_id": "hufsky-data-retention",
            "start_s": 0.0,
            "end_s": 15.0,
            "visual_caption": "people holding a sign",
            "ocr_text": "FREIHEIT",
            "transcript_text": "",
        }
    ]
    record, warning = align_query(spec, transcripts={}, segments=segments)
    assert record["label_source"] == "frame"
    assert record["relevant_spans"] == [[26.2, 29.8, 2]]
    assert "kept the frame times" in warning


def test_umlaut_in_ocr_matches_the_folded_phrase():
    spec = {
        "query_id": "hufsky-demokratie",
        "query": "Demokratie braucht Anonymität",
        "type": "visual",
        "video_id": "hufsky-data-retention",
        "split": "test",
        "phrases": ["anonymitat"],
        "fallback_spans": [[26.2, 29.8, 2]],
    }
    segments = [
        {
            "video_id": "hufsky-data-retention",
            "start_s": 26.0,
            "end_s": 30.0,
            "visual_caption": "",
            "ocr_text": "DEMOKRATIE BRAUCHT ANONYMITÄT",
            "transcript_text": "",
        }
    ]
    record, _warning = align_query(spec, transcripts={}, segments=segments)
    assert record["label_source"] == "caption"
    assert record["relevant_spans"] == [[26.0, 30.0, 2]]


def _spoken_miss(query_id: str = "tree-talk") -> dict:
    return {
        "query_id": query_id,
        "query": "talk and sing",
        "type": "spoken",
        "video_id": "talking-tree-2011",
        "split": "test",
        "phrases": ["talk and see"],
    }


def test_phrase_miss_warns_and_keeps_previous_spans():
    existing = {
        "query_id": "tree-talk",
        "query": "talk and see",
        "type": "spoken",
        "video_id": "talking-tree-2011",
        "relevant_spans": [[16.1, 17.56, 2]],
        "split": "test",
        "label_source": "transcript-words",
    }
    record, warning = align_query(
        _spoken_miss(),
        transcripts={"talking-tree-2011": {"segments": []}},
        segments=[],
        existing=existing,
    )
    assert record is not None
    assert record["relevant_spans"] == [[16.1, 17.56, 2]]
    assert record["kept_previous"] is True
    assert "kept the spans already in the output file" in warning


def test_phrase_miss_without_anything_to_keep_does_not_abort():
    record, warning = align_query(
        _spoken_miss("missing"),
        transcripts={},
        segments=[],
    )
    assert record is None
    assert "left out of the output" in warning


def test_strict_phrase_miss_exits():
    with pytest.raises(SystemExit):
        align_query(
            _spoken_miss(),
            transcripts={},
            segments=[],
            strict=True,
        )


def test_cloud_query_file_covers_three_clips_and_grades():
    path = Path(__file__).resolve().parents[1] / "queries.cloud.jsonl"
    rows = load_jsonl(path)
    assert len(rows) >= 28
    videos = {row["video_id"] for row in rows}
    assert videos == {"edison-1920s", "hufsky-data-retention", "talking-tree-2011"}
    types = {row["type"] for row in rows}
    assert {"spoken", "visual", "negative"} <= types
    hufsky = [row for row in rows if row["video_id"] == "hufsky-data-retention" and row["type"] != "negative"]
    assert hufsky
    graded = [
        span
        for row in rows
        if row["type"] != "negative"
        for span in row["relevant_spans"]
        if len(span) == 3 and span[2] == 2
    ]
    assert graded
    assert any(row["type"] == "negative" and row["relevant_spans"] == [] for row in rows)
    # The spec is what you rerun. The jsonl is one alignment of it.
    talk = next(row for row in rows if row["query_id"] == "tree-talk")
    assert talk["query"] == "talk and sing"
    assert talk["relevant_spans"][0][:2] == [16.14, 17.56]
    spec = Path(__file__).resolve().parents[1] / "queries.cloud.spec.jsonl"
    spec_rows = [json.loads(line) for line in spec.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(spec_rows) >= len(rows)
    talk_spec = next(row for row in spec_rows if row["query_id"] == "tree-talk")
    assert talk_spec["phrases"] == ["talk and sing", "we talk and sing"]
