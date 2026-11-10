"""Run Recall@k, MRR, and nDCG for one retriever configuration.

Both of these work from the repo root:

  python eval/run_eval.py --queries eval/queries.sample.jsonl --split test --out eval/results/sample
  python -m eval.run_eval --queries eval/queries.sample.jsonl --split test --out eval/results/sample
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# `python eval/run_eval.py` puts this file's directory on sys.path[0], so
# `import eval` looks for eval/eval and raises ModuleNotFoundError. The repo
# root has to come first. `python -m eval.run_eval` already has the root
# (the cwd) on the path; inserting it again is harmless.
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services"), str(ROOT / "services" / "api")]

from eval.metrics import evaluate, to_markdown  # noqa: E402
from eval.schema import load_jsonl  # noqa: E402

ABLATIONS = {
    "sparse": {"use_text_dense": False, "use_visual_dense": False, "use_sparse": True, "rerank": False},
    "text_dense": {"use_text_dense": True, "use_visual_dense": False, "use_sparse": False, "rerank": False},
    "text_visual": {"use_text_dense": True, "use_visual_dense": True, "use_sparse": False, "rerank": False},
    "hybrid": {"use_text_dense": True, "use_visual_dense": True, "use_sparse": True, "rerank": False},
    "hybrid_rerank": {
        "use_text_dense": True,
        "use_visual_dense": True,
        "use_sparse": True,
        "rerank": True,
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate VideoMind retrieval")
    parser.add_argument("--queries", type=Path, default=Path("eval/queries.sample.jsonl"))
    parser.add_argument("--split", default="test", choices=["dev", "test", "all"])
    parser.add_argument("--ablation", default="hybrid_rerank", choices=[*ABLATIONS, "all"])
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("eval/results/sample"))
    args = parser.parse_args()

    from pipeline.config import get_settings
    from pipeline.runtime import Resources

    rows = load_jsonl(args.queries)
    if args.split != "all":
        rows = [row for row in rows if row["split"] == args.split]
    if not rows:
        raise SystemExit("no queries matched")

    settings = get_settings()
    resources = Resources(settings)
    names = list(ABLATIONS) if args.ablation == "all" else [args.ablation]
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        for name in names:
            flags = ABLATIONS[name]

            def search_fn(query: str, video_id: str | None, flags=flags):
                hits, _ = resources.retriever.search(
                    query, k=args.k, video_id=video_id or None, **flags
                )
                return [{"start_s": hit.start_s, "end_s": hit.end_s} for hit in hits]

            report = evaluate(rows, search_fn)
            report["ablation"] = name
            report["note"] = (
                "Computed on the query file you passed. "
                "Do not paste these numbers into the README ablation table "
                "unless this file is the frozen labeled test split."
            )
            (args.out / f"{name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            (args.out / f"{name}.md").write_text(
                to_markdown(f"VideoMind {name}", report), encoding="utf-8"
            )
            overall = report["overall"]
            extra = ""
            if report.get("hard_negatives"):
                extra = f" hard_negatives={report['hard_negatives']} (not in the averages)"
            print(
                f"{name}: n={overall['n']} R@1={overall['recall@1']:.3f} "
                f"R@5={overall['recall@5']:.3f} MRR@10={overall['mrr@10']:.3f} "
                f"nDCG@10={overall['ndcg@10']:.3f}{extra}"
            )
    finally:
        resources.close()


if __name__ == "__main__":
    main()
