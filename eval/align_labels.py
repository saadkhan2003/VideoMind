"""Turn a query spec into graded spans from a transcript and caption text.

Spoken and keyword queries are aligned to word timestamps when a transcript
JSON file is available, and otherwise to a segment whose transcript contains
the phrase. Visual queries prefer a segment whose caption or OCR text contains
the phrase. If the caption text does not, the frame times in the spec are kept
and a warning is printed.

A spoken phrase that is missing does not abort the file. The default warns and
keeps fallback spans or the spans already in ``--out``. ``--strict`` exits
instead, which is the previous behaviour. A spec line with ``on_miss: skip``
still drops that one query. ``on_miss: error`` still aborts.

This does not call OpenRouter or any other paid API. Point it at files you
already have, or at the object store already configured in the environment.

From the repo root:

  python -m eval.align_labels \\
    --spec eval/queries.cloud.spec.jsonl \\
    --transcripts "$DATA_DIR" \\
    --db "$DATA_DIR/videomind.db" \\
    --from-store \\
    --out eval/queries.cloud.jsonl

  python eval/align_labels.py --spec eval/queries.cloud.spec.jsonl \\
    --transcripts /path/to/transcripts --out eval/queries.cloud.jsonl

Transcript files are read from the first path that exists:

  <dir>/<video_id>.json
  <dir>/<video_id>/transcript.json
  <dir>/videos/<video_id>/transcript.json
  <dir>/objects/videos/<video_id>/transcript.json

``--from-store`` reads ``videos/<video_id>/transcript.json`` with the same
storage settings as ingest (R2 when the R2 variables are set, otherwise the
local object dir). ``--db`` reads the ``segments`` table for transcript,
caption, and OCR text. ``--captions`` is a JSONL file of those same fields.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services"), str(ROOT / "services" / "api")]

from eval.schema import validate_record  # noqa: E402

_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss", "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u"})
_TOKEN = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower().translate(_FOLD))


def transcript_words(document: dict) -> list[tuple[str, float, float]]:
    words: list[tuple[str, float, float]] = []
    for segment in document.get("segments") or []:
        for word in segment.get("words") or []:
            tokens = tokenize(str(word.get("word") or ""))
            if len(tokens) != 1:
                continue
            start = float(word["start"])
            end = float(word["end"])
            # Whisper sometimes stamps a word with start == end. Keep the token
            # so a phrase can still match; the span uses the neighboring times.
            if end < start:
                continue
            words.append((tokens[0], start, end))
    return words


def find_phrase_spans(
    words: list[tuple[str, float, float]],
    phrase: str,
    *,
    grade: int = 2,
    demote_repeats: bool = False,
    merge_gap_s: float = 3.0,
) -> list[list[float | int]]:
    """Grade 2 on the first hit. Later hits are grade 1 when ``demote_repeats`` is set.

    Hits closer than ``merge_gap_s`` collapse into one span so two words inside
    the same breath are not two relevance labels.
    """
    wanted = tokenize(phrase)
    if not wanted:
        return []
    found: list[list[float | int]] = []
    index = 0
    width = len(wanted)
    while index <= len(words) - width:
        if [words[index + offset][0] for offset in range(width)] == wanted:
            start = words[index][1]
            end = words[index + width - 1][2]
            if end <= start:
                end = start + 0.05
            this_grade = grade if not found or not demote_repeats else 1
            found.append([round(start, 3), round(end, 3), this_grade])
            index += width
        else:
            index += 1
    return _merge_close(found, merge_gap_s)


def _merge_close(spans: list[list[float | int]], gap: float) -> list[list[float | int]]:
    if not spans:
        return []
    merged: list[list[float | int]] = [list(spans[0])]
    for start, end, grade in spans[1:]:
        previous = merged[-1]
        if float(start) - float(previous[1]) <= gap:
            previous[1] = round(max(float(previous[1]), float(end)), 3)
            previous[2] = max(int(previous[2]), int(grade))
        else:
            merged.append([start, end, grade])
    return merged


def segments_containing(segments: list[dict], video_id: str, phrase: str, fields: tuple[str, ...]) -> list[dict]:
    wanted = tokenize(phrase)
    if not wanted:
        return []
    hits = []
    for row in segments:
        if row.get("video_id") != video_id:
            continue
        text = " ".join(str(row.get(field) or "") for field in fields)
        tokens = tokenize(text)
        if _contains(tokens, wanted):
            hits.append(row)
    hits.sort(key=lambda row: float(row["start_s"]))
    return hits


def _contains(tokens: list[str], wanted: list[str]) -> bool:
    width = len(wanted)
    if width == 0 or len(tokens) < width:
        return False
    for index in range(len(tokens) - width + 1):
        if tokens[index : index + width] == wanted:
            return True
    return False


def _segment_spans(rows: list[dict], grade: int, demote_repeats: bool) -> list[list[float | int]]:
    spans = []
    for index, row in enumerate(rows):
        start = round(float(row["start_s"]), 3)
        end = round(float(row["end_s"]), 3)
        if end <= start:
            continue
        this_grade = grade if index == 0 or not demote_repeats else 1
        spans.append([start, end, this_grade])
    return spans


def align_query(
    spec: dict,
    *,
    transcripts: dict[str, dict],
    segments: list[dict],
    existing: dict | None = None,
    strict: bool = False,
) -> tuple[dict | None, str]:
    """Return ``(record, warning)``. ``record`` is None when the query is left out.

    A phrase miss warns and keeps a fallback span or the spans already in the
    output file. ``--strict`` (or ``on_miss: error``) is the old abort.
    ``on_miss: skip`` leaves the query out without aborting.
    """
    video_id = spec["video_id"]
    query_type = spec["type"]
    if query_type == "negative":
        record = _base_record(spec, [])
        record["hard_negative"] = True
        record["label_source"] = "negative"
        return record, ""

    phrases = list(spec.get("phrases") or [])
    grade = int(spec.get("grade") or 2)
    demote = bool(spec.get("demote_repeats"))
    on_miss = _miss_mode(spec, strict=strict)

    if query_type in {"spoken", "keyword"}:
        document = transcripts.get(video_id)
        if document:
            for phrase in phrases:
                spans = find_phrase_spans(
                    transcript_words(document),
                    phrase,
                    grade=grade,
                    demote_repeats=demote,
                )
                if spans:
                    record = _base_record(spec, spans)
                    record["label_source"] = "transcript-words"
                    record["matched_phrase"] = phrase
                    return record, ""
        for phrase in phrases:
            rows = segments_containing(segments, video_id, phrase, ("transcript_text", "ocr_text"))
            if rows:
                record = _base_record(spec, _segment_spans(rows, grade, demote))
                record["label_source"] = "segment-text"
                record["matched_phrase"] = phrase
                return record, ""
        return _on_miss(
            spec,
            on_miss,
            existing,
            f"none of {phrases} was found for {video_id}",
        )

    fallback = [list(span) for span in spec.get("fallback_spans") or []]
    caption_rows: list[dict] = []
    matched = ""
    for phrase in phrases:
        rows = segments_containing(segments, video_id, phrase, ("visual_caption", "ocr_text"))
        if rows:
            caption_rows = rows
            matched = phrase
            break
    if caption_rows:
        record = _base_record(spec, _segment_spans(caption_rows, grade, demote))
        record["label_source"] = "caption"
        record["matched_phrase"] = matched
        return record, ""
    if fallback:
        record = _base_record(spec, fallback)
        record["label_source"] = "frame"
        warning = ""
        if phrases and segments:
            warning = (
                f"{spec['query_id']}: caption/OCR text did not contain {phrases}; "
                "kept the frame times from the spec"
            )
        return record, warning
    return _on_miss(spec, on_miss, existing, "visual query has no fallback_spans and no caption match")


def _miss_mode(spec: dict, *, strict: bool) -> str:
    explicit = spec.get("on_miss")
    if explicit:
        return str(explicit)
    return "error" if strict else "keep"


def _on_miss(spec: dict, mode: str, existing: dict | None, reason: str) -> tuple[dict | None, str]:
    query_id = spec["query_id"]
    if mode == "skip":
        return None, f"skipped {query_id}: {reason}"
    if mode == "error":
        raise SystemExit(
            f"{query_id}: {reason}. "
            "Re-run without --strict to warn and keep the previous spans, or set on_miss to skip."
        )
    fallback = [list(span) for span in spec.get("fallback_spans") or []]
    if fallback:
        record = _base_record(spec, fallback)
        record["label_source"] = "kept-fallback"
        return record, f"{query_id}: {reason}; kept the fallback spans"
    spans = (existing or {}).get("relevant_spans") or []
    if spans:
        record = _base_record(spec, spans)
        if existing and existing.get("label_source"):
            record["label_source"] = existing["label_source"]
        if existing and existing.get("matched_phrase"):
            record["matched_phrase"] = existing["matched_phrase"]
        record["kept_previous"] = True
        return record, f"{query_id}: {reason}; kept the spans already in the output file"
    return None, f"{query_id}: {reason}; nothing to keep, so this query was left out of the output"


def _base_record(spec: dict, spans: list) -> dict:
    record = {
        "query_id": spec["query_id"],
        "query": spec["query"],
        "type": spec["type"],
        "video_id": spec["video_id"],
        "relevant_spans": spans,
        "split": spec.get("split") or "test",
    }
    if spec.get("note"):
        record["note"] = spec["note"]
    return record


def align_all(
    specs: list[dict],
    *,
    transcripts: dict[str, dict],
    segments: list[dict],
    existing: dict[str, dict] | None = None,
    strict: bool = False,
) -> tuple[list[dict], list[str]]:
    records = []
    warnings = []
    previous = existing or {}
    for spec in specs:
        record, warning = align_query(
            spec,
            transcripts=transcripts,
            segments=segments,
            existing=previous.get(spec["query_id"]),
            strict=strict,
        )
        if warning:
            warnings.append(warning)
        if record is not None:
            validate_record(record)
            records.append(record)
    return records, warnings


def load_specs(path: Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: {exc}") from exc
    return rows


def load_transcripts(directory: Path, video_ids: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for video_id in video_ids:
        for path in _transcript_candidates(directory, video_id):
            if path.is_file():
                found[video_id] = json.loads(path.read_text(encoding="utf-8"))
                break
    return found


def _transcript_candidates(directory: Path, video_id: str) -> list[Path]:
    return [
        directory / f"{video_id}.json",
        directory / video_id / "transcript.json",
        directory / "videos" / video_id / "transcript.json",
        directory / "objects" / "videos" / video_id / "transcript.json",
    ]


def load_caption_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_segments_db(path: Path) -> list[dict]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(
            "select video_id, start_s, end_s, transcript_text, visual_caption, ocr_text from segments"
        )
        return [dict(row) for row in cursor]
    finally:
        connection.close()


def load_transcripts_from_store(video_ids: list[str]) -> dict[str, dict]:
    """Read transcript objects already stored by ingest. No caption API calls."""
    from pipeline.config import get_settings
    from pipeline.storage import build_store

    store = build_store(get_settings())
    found: dict[str, dict] = {}
    for video_id in video_ids:
        key = f"videos/{video_id}/transcript.json"
        try:
            raw = store.get_bytes(key)
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not read {key}: {type(exc).__name__}: {exc}")
            continue
        found[video_id] = json.loads(raw)
    return found


def load_existing(path: Path) -> dict[str, dict]:
    """Rows already in ``--out``. A miss keeps these spans instead of aborting."""
    if not path.is_file():
        return {}
    found: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        query_id = row.get("query_id")
        if query_id:
            found[str(query_id)] = row
    return found


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Align eval queries to stored transcripts and captions")
    parser.add_argument("--spec", type=Path, default=Path("eval/queries.cloud.spec.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("eval/queries.cloud.jsonl"))
    parser.add_argument("--transcripts", type=Path, default=None, help="Directory of transcript JSON files")
    parser.add_argument("--captions", type=Path, default=None, help="JSONL of segment caption rows")
    parser.add_argument("--db", type=Path, default=None, help="SQLite database with a segments table")
    parser.add_argument(
        "--from-store",
        action="store_true",
        help="Read videos/<id>/transcript.json from the configured object store (R2 or local disk)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit if a phrase is missing and the spec does not set on_miss. "
            "The default warns and keeps fallback or previous spans."
        ),
    )
    args = parser.parse_args(argv)
    specs = load_specs(args.spec)
    video_ids = sorted({spec["video_id"] for spec in specs})
    transcripts: dict[str, dict] = {}
    if args.transcripts:
        transcripts.update(load_transcripts(args.transcripts, video_ids))
    if args.from_store:
        for video_id, document in load_transcripts_from_store(video_ids).items():
            transcripts.setdefault(video_id, document)
    segments: list[dict] = []
    if args.db:
        segments.extend(load_segments_db(args.db))
    if args.captions:
        segments.extend(load_caption_jsonl(args.captions))
    records, warnings = align_all(
        specs,
        transcripts=transcripts,
        segments=segments,
        existing=load_existing(args.out),
        strict=args.strict,
    )
    for warning in warnings:
        print(f"warning: {warning}")
    write_jsonl(args.out, records)
    by_type: dict[str, int] = {}
    for record in records:
        by_type[record["type"]] = by_type.get(record["type"], 0) + 1
    print(f"wrote {len(records)} queries to {args.out} ({by_type})")


if __name__ == "__main__":
    main()
