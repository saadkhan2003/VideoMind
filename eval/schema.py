from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ("query_id", "query", "type", "video_id", "relevant_spans", "split")
TYPES = {"spoken", "visual", "keyword", "negative"}
SPLITS = {"dev", "test"}
GRADES = {1, 2}


def parse_span(span: list | tuple) -> tuple[float, float, int]:
    if not isinstance(span, (list, tuple)) or len(span) not in (2, 3):
        raise ValueError(f"bad span {span}")
    start, end = float(span[0]), float(span[1])
    if end <= start:
        raise ValueError(f"bad span {span}")
    if len(span) == 2:
        return start, end, 1
    grade = span[2]
    if isinstance(grade, bool) or not isinstance(grade, (int, float)) or float(grade) not in GRADES:
        raise ValueError(f"grade must be 1 or 2, got {span}")
    return start, end, int(grade)


def validate_record(record: dict) -> None:
    missing = [key for key in REQUIRED if key not in record]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    if record["type"] not in TYPES:
        raise ValueError(f"type must be one of {sorted(TYPES)}")
    if record["split"] not in SPLITS:
        raise ValueError("split must be dev or test")
    if not str(record["query"]).strip():
        raise ValueError("query is empty")
    spans = record["relevant_spans"]
    if not isinstance(spans, list):
        raise ValueError("relevant_spans must be a list")
    if record["type"] == "negative":
        if spans:
            raise ValueError("a negative query has no relevant spans")
        return
    if not spans:
        raise ValueError("relevant_spans must be a non-empty list")
    for span in spans:
        parse_span(span)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        try:
            validate_record(record)
        except ValueError as exc:
            raise ValueError(f"{path}:{line_no}: {exc}") from exc
        rows.append(record)
    return rows


def append_record(path: Path, record: dict) -> None:
    validate_record(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
