"""Retrieval metrics for timestamped segments.

Hit rule: a retrieved segment is relevant when it contains the midpoint of a
labeled relevant span. A span credits only the first segment that covers it.
The gain is the span grade (1 partial, 2 exact). A two-item span counts as
grade 1, which is the old binary label.

Hard-negative queries (type ``negative``) have no relevant span. They are
reported and left out of the Recall, MRR, and nDCG averages: the retriever
always returns neighbors, so scoring them as misses would zero the metric.
"""

from __future__ import annotations

import math
from collections import defaultdict


def contains_midpoint(start: float, end: float, span: list[float] | tuple[float, float]) -> bool:
    mid = (float(span[0]) + float(span[1])) / 2
    return start - 1e-6 <= mid <= end + 1e-6


def span_grade(span: list | tuple) -> int:
    if len(span) >= 3:
        return int(span[2])
    return 1


def relevance_flags(results: list[dict], spans: list) -> list[int]:
    remaining = [(float(span[0]), float(span[1]), span_grade(span)) for span in spans]
    flags: list[int] = []
    for result in results:
        matched = None
        for index, span in enumerate(remaining):
            if contains_midpoint(float(result["start_s"]), float(result["end_s"]), span):
                matched = index
                break
        if matched is None:
            flags.append(0)
        else:
            flags.append(remaining.pop(matched)[2])
    return flags


def recall_at_k(flags: list[int], k: int) -> float:
    return 1.0 if any(flags[:k]) else 0.0


def reciprocal_rank(flags: list[int], k: int) -> float:
    for index, flag in enumerate(flags[:k], start=1):
        if flag:
            return 1.0 / index
    return 0.0


def dcg(flags: list[int]) -> float:
    total = 0.0
    for index, flag in enumerate(flags):
        gain = float(flag)
        if gain:
            total += gain / math.log2(index + 2)
    return total


def ndcg_at_k(
    flags: list[int],
    k: int,
    n_relevant: int | None = None,
    *,
    ideal_gains: list[int] | None = None,
) -> float:
    if ideal_gains is None:
        if not n_relevant or n_relevant <= 0:
            return 0.0
        ideal_gains = [1] * int(n_relevant)
    else:
        ideal_gains = [int(gain) for gain in ideal_gains if gain]
        if not ideal_gains:
            return 0.0
    gained = flags[:k]
    ideal = dcg(sorted(ideal_gains, reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg(gained) / ideal


def is_hard_negative(query: dict) -> bool:
    return query.get("type") == "negative" or bool(query.get("hard_negative"))


def evaluate(queries: list[dict], search_fn, ks: tuple[int, ...] = (1, 5, 10)) -> dict:
    """search_fn(query: str, video_id: str) -> ranked list of {start_s, end_s}."""
    max_k = max(ks)
    per_query = []
    buckets: dict[str, list] = defaultdict(list)
    hard_negatives = 0
    for query in queries:
        row = {
            "query_id": query.get("query_id"),
            "type": query.get("type", ""),
            "split": query.get("split", ""),
        }
        if is_hard_negative(query):
            hard_negatives += 1
            row["hard_negative"] = True
            row["scored"] = False
            per_query.append(row)
            continue
        results = list(search_fn(query["query"], query.get("video_id")))
        spans = query.get("relevant_spans") or []
        flags = relevance_flags(results, spans)
        grades = [span_grade(span) for span in spans]
        for k in ks:
            row[f"recall@{k}"] = recall_at_k(flags, k)
        row["mrr@10"] = reciprocal_rank(flags, min(10, max_k))
        row["ndcg@10"] = ndcg_at_k(flags, min(10, max_k), ideal_gains=grades)
        row["first_relevant_rank"] = next((i for i, flag in enumerate(flags, 1) if flag), None)
        row["scored"] = True
        per_query.append(row)
        buckets[row["type"] or "unknown"].append(row)
        buckets["__all__"].append(row)

    def average(rows: list[dict]) -> dict:
        if not rows:
            empty = {f"recall@{k}": 0.0 for k in ks}
            empty["mrr@10"] = 0.0
            empty["ndcg@10"] = 0.0
            empty["n"] = 0
            return empty
        out = {"n": len(rows)}
        keys = [f"recall@{k}" for k in ks] + ["mrr@10", "ndcg@10"]
        for key in keys:
            out[key] = sum(row[key] for row in rows) / len(rows)
        return out

    by_type = {name: average(rows) for name, rows in buckets.items() if name != "__all__"}
    return {
        "hit_rule": (
            "A hit is a segment that contains the midpoint of a relevant span. "
            "Each span credits only the first covering segment. "
            "Gain is the span grade (default 1; 2 is an exact mention). "
            "Hard negatives are excluded from the averages."
        ),
        "n_queries": len(queries),
        "n_scored": sum(1 for row in per_query if row.get("scored")),
        "hard_negatives": hard_negatives,
        "overall": average(buckets.get("__all__", [])),
        "by_type": by_type,
        "per_query": per_query,
    }


def to_markdown(title: str, report: dict) -> str:
    header = "| Retriever | R@1 | R@5 | R@10 | MRR@10 | nDCG@10 |"
    sep = "|---|---|---|---|---|---|"
    overall = report["overall"]

    def cells(name: str, stats: dict) -> str:
        def fmt(key: str) -> str:
            value = stats.get(key)
            if value is None:
                return ""
            return f"{value:.3f}"

        return (
            f"| {name} | {fmt('recall@1')} | {fmt('recall@5')} | {fmt('recall@10')} | "
            f"{fmt('mrr@10')} | {fmt('ndcg@10')} |"
        )

    lines = [f"# {title}", "", header, sep, cells("this run", overall), ""]
    if report.get("by_type"):
        lines.extend(["## By query type", "", header, sep])
        for name, stats in sorted(report["by_type"].items()):
            lines.append(cells(name, stats))
        lines.append("")
    lines.append(report["hit_rule"])
    if report.get("hard_negatives"):
        lines.append(
            f"Hard negatives in this file: {report['hard_negatives']}. They are not included in the averages."
        )
    lines.append("")
    return "\n".join(lines)
