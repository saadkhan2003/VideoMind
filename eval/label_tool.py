"""Add labeled queries to a JSONL file.

  python eval/label_tool.py add eval/queries.sample.jsonl \
    --id q7 --query "when is the diagram shown" --type visual \
    --video sample-lecture --start 16 --end 24 --split dev

  python eval/label_tool.py validate eval/queries.sample.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services"), str(ROOT / "services" / "api")]

from eval.schema import append_record, load_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Label VideoMind eval queries")
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add")
    add.add_argument("path", type=Path)
    add.add_argument("--id", required=True)
    add.add_argument("--query", required=True)
    add.add_argument("--type", required=True, choices=["spoken", "visual", "keyword", "negative"])
    add.add_argument("--video", required=True)
    add.add_argument("--start", type=float, default=None)
    add.add_argument("--end", type=float, default=None)
    add.add_argument("--grade", type=int, default=1, choices=[1, 2])
    add.add_argument("--split", default="dev", choices=["dev", "test"])

    check = sub.add_parser("validate")
    check.add_argument("path", type=Path)

    args = parser.parse_args()
    if args.cmd == "validate":
        rows = load_jsonl(args.path)
        print(f"{len(rows)} queries ok in {args.path}")
        return
    if args.type == "negative":
        spans: list = []
    else:
        if args.start is None or args.end is None:
            raise SystemExit("--start and --end are required unless --type negative")
        spans = [[args.start, args.end, args.grade]]
    record = {
        "query_id": args.id,
        "query": args.query,
        "type": args.type,
        "video_id": args.video,
        "relevant_spans": spans,
        "split": args.split,
    }
    append_record(args.path, record)
    print(f"added {args.id}")


if __name__ == "__main__":
    main()
