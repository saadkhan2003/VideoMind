import math

import pytest

from eval.metrics import evaluate, ndcg_at_k, recall_at_k, reciprocal_rank, relevance_flags
from eval.schema import append_record, load_jsonl, validate_record


def test_single_query_matches_hand_computed_scores():
    # One relevant span, midpoint 15. Ranking: miss, hit, another hit of the same span.
    results = [
        {"start_s": 0, "end_s": 5},
        {"start_s": 10, "end_s": 20},
        {"start_s": 12, "end_s": 18},
    ]
    flags = relevance_flags(results, [[10, 20]])
    assert flags == [0, 1, 0]
    assert recall_at_k(flags, 1) == 0.0
    assert recall_at_k(flags, 5) == 1.0
    assert reciprocal_rank(flags, 10) == 0.5
    # DCG = 1/log2(3), IDCG = 1, nDCG = 1/log2(3)
    assert ndcg_at_k(flags, 10, n_relevant=1) == pytest.approx(1 / math.log2(3))
    assert ndcg_at_k(flags, 10, n_relevant=1) == pytest.approx(0.6309297535714574)


def test_macro_average_of_two_queries():
    queries = [
        {
            "query_id": "a",
            "query": "a",
            "type": "spoken",
            "video_id": "v",
            "relevant_spans": [[10, 20]],
            "split": "test",
        },
        {
            "query_id": "b",
            "query": "b",
            "type": "visual",
            "video_id": "v",
            "relevant_spans": [[0, 4]],
            "split": "test",
        },
    ]

    def search(query, video_id):
        del video_id
        if query == "a":
            return [
                {"start_s": 0, "end_s": 5},
                {"start_s": 10, "end_s": 20},
                {"start_s": 12, "end_s": 18},
            ]
        return [{"start_s": 0, "end_s": 4}]

    report = evaluate(queries, search)
    assert report["overall"]["recall@1"] == pytest.approx(0.5)
    assert report["overall"]["mrr@10"] == pytest.approx(0.75)
    assert report["overall"]["ndcg@10"] == pytest.approx((1 / math.log2(3) + 1) / 2)
    assert report["by_type"]["visual"]["recall@1"] == 1.0
    assert report["n_queries"] == 2


def test_graded_gain_lowers_ndcg_when_the_weaker_span_ranks_first():
    results = [
        {"start_s": 0, "end_s": 5},
        {"start_s": 10, "end_s": 20},
    ]
    spans = [[10, 20, 2], [0, 4, 1]]
    flags = relevance_flags(results, spans)
    assert flags == [1, 2]
    score = ndcg_at_k(flags, 10, ideal_gains=[2, 1])
    ideal = (2 / math.log2(2)) + (1 / math.log2(3))
    gained = (1 / math.log2(2)) + (2 / math.log2(3))
    assert score == pytest.approx(gained / ideal)
    assert score < 1


def test_hard_negative_is_excluded_from_the_average():
    queries = [
        {
            "query_id": "hit",
            "query": "experiment",
            "type": "spoken",
            "video_id": "v",
            "relevant_spans": [[10, 20, 2]],
            "split": "test",
        },
        {
            "query_id": "neg",
            "query": "how do you knead sourdough",
            "type": "negative",
            "video_id": "v",
            "relevant_spans": [],
            "split": "test",
            "hard_negative": True,
        },
    ]

    def search(query, video_id):
        del query, video_id
        return [{"start_s": 10, "end_s": 20}]

    report = evaluate(queries, search)
    assert report["n_queries"] == 2
    assert report["hard_negatives"] == 1
    assert report["n_scored"] == 1
    assert report["overall"]["n"] == 1
    assert report["overall"]["recall@1"] == 1.0
    assert report["per_query"][1]["scored"] is False


def test_label_file_round_trip(tmp_path):
    path = tmp_path / "queries.jsonl"
    record = {
        "query_id": "q",
        "query": "when is the chart shown",
        "type": "visual",
        "video_id": "vid",
        "relevant_spans": [[1, 2]],
        "split": "dev",
    }
    validate_record(record)
    append_record(path, record)
    assert load_jsonl(path) == [record]
    with pytest.raises(ValueError):
        validate_record({**record, "type": "other"})
    graded = {**record, "relevant_spans": [[1, 2, 2]]}
    validate_record(graded)
    with pytest.raises(ValueError):
        validate_record({**record, "relevant_spans": [[1, 2, 3]]})
    negative = {**record, "type": "negative", "relevant_spans": []}
    validate_record(negative)
    with pytest.raises(ValueError):
        validate_record({**negative, "relevant_spans": [[1, 2]]})
