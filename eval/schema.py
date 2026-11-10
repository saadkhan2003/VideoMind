from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ("query_id", "query", "type", "video_id", "relevant_spans", "split")
TYPES = {"spoken", "visual", "keyword"}
SPLITS = {"dev", "test"}


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
    if not isinstance(spans, list) or not spans:
        raise ValueError("relevant_spans must be a non-empty list")
    for span in spans:
        if (
            not isinstance(span, (list, tuple))
            or len(span) != 2
            or float(span[1]) <= float(span[0])
        ):
            raise ValueError(f"bad span {span}")


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
