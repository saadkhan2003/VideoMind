from pipeline.embed import HashEmbedder, tokenize
from pipeline.index import SegmentIndex, build_qdrant, point_id
from pipeline.rerank import CrossEncoderReranker, LexicalReranker
from pipeline.retrieve import Retriever
from pipeline.rrf import reciprocal_rank_fusion
from pipeline.sparse import sparse_vector
from pipeline.testing import make_settings


def test_rrf_formula_matches_hand_calculation():
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60)
    scores = dict(fused)
    assert scores["a"] == (1 / 61) + (0)
    assert scores["b"] == (1 / 62) + (1 / 61)
    assert scores["c"] == 1 / 62
    assert fused[0][0] == "b"
    assert fused[1][0] == "a"


def test_hash_embedder_ranks_shared_tokens_higher():
    embedder = HashEmbedder(64)
    left, right, other = embedder.embed(
        ["backpropagation gradient", "backpropagation explained", "pasta recipe tomato"]
    )
    assert _cosine(left, right) > _cosine(left, other)


def test_sparse_vector_is_stable_and_marks_query_terms():
    indices, values = sparse_vector("Backpropagation backpropagation loss")
    assert indices == sorted(indices)
    assert len(indices) == len(set(indices))
    assert len(tokenize("backpropagation loss")) == 2
    assert values[indices.index(_index("backpropagation"))] == 2.0


def test_lexical_reranker_prefers_the_overlapping_document():
    reranker = LexicalReranker()
    scores = reranker.score("architecture diagram", ["pasta sauce", "the architecture diagram is shown"])
    assert scores[1] > scores[0]


def test_cross_encoder_wrapper_uses_the_bge_model_name():
    class Fake:
        def predict(self, pairs):
            return [float(len(doc)) for _, doc in pairs]

    reranker = CrossEncoderReranker(model=Fake())
    assert reranker.model_name == "BAAI/bge-reranker-v2-m3"
    assert reranker.score("q", ["aa", "abcd"]) == [2.0, 4.0]


def test_hybrid_search_finds_spoken_and_visual_moments(tmp_path):
    settings = make_settings(tmp_path, reranker_enabled=False)
    client = build_qdrant(settings)
    index = SegmentIndex(client, settings)
    embedder = HashEmbedder(settings.embedding_dim)
    docs = [
        ("s1", 8, 16, "we explain backpropagation and the gradient", "", ""),
        ("s2", 16, 24, "here is the next slide", "architecture diagram of the network", "Architecture Diagram"),
        ("s3", 24, 32, "the loss function is mean squared error", "", ""),
    ]
    points = []
    for seg_id, start, end, transcript, caption, ocr in docs:
        text_vec = embedder.embed([transcript])[0]
        visual_vec = embedder.embed([f"{caption} {ocr}".strip() or " "])[0]
        indices, values = sparse_vector(" ".join([transcript, caption, ocr]))
        points.append(
            {
                "id": point_id("sample", start),
                "text_dense": text_vec,
                "visual_dense": visual_vec,
                "sparse_indices": indices,
                "sparse_values": values,
                "payload": {
                    "segment_id": seg_id,
                    "video_id": "sample",
                    "title": "Sample",
                    "start_s": start,
                    "end_s": end,
                    "transcript_text": transcript,
                    "visual_caption": caption,
                    "ocr_text": ocr,
                    "keyframe_url": "",
                    "lang": "en",
                },
            }
        )
    index.upsert(points)
    retriever = Retriever(index, settings, embedder, reranker=None)
    spoken, _ = retriever.search("backpropagation", k=3, rerank=False)
    assert spoken[0].segment_id == "s1"
    visual, _ = retriever.search(
        "architecture diagram",
        k=3,
        use_text_dense=False,
        use_sparse=False,
        use_visual_dense=True,
        rerank=False,
    )
    assert visual[0].segment_id == "s2"
    keyword, _ = retriever.search("mean squared error", k=3, use_text_dense=False, use_visual_dense=False, rerank=False)
    assert keyword[0].segment_id == "s3"
    filtered, _ = retriever.search("backpropagation", k=3, video_id="missing", rerank=False)
    assert filtered == []
    index.delete_video("sample")
    index.upsert(points)
    assert index.count() == 3
    index.delete_video("sample")
    index.upsert(points)
    assert index.count() == 3


def test_rerank_can_be_disabled(tmp_path):
    settings = make_settings(tmp_path, reranker_enabled=True)

    class Boom:
        model_name = "boom"

        def score(self, query, documents):
            raise AssertionError("reranker should not run")

    client = build_qdrant(settings)
    index = SegmentIndex(client, settings)
    embedder = HashEmbedder(settings.embedding_dim)
    text = "backpropagation"
    indices, values = sparse_vector(text)
    index.upsert(
        [
            {
                "id": point_id("v", 0),
                "text_dense": embedder.embed([text])[0],
                "visual_dense": embedder.embed([" "])[0],
                "sparse_indices": indices,
                "sparse_values": values,
                "payload": {
                    "segment_id": "only",
                    "video_id": "v",
                    "title": "t",
                    "start_s": 0,
                    "end_s": 5,
                    "transcript_text": text,
                    "visual_caption": "",
                    "ocr_text": "",
                    "keyframe_url": "",
                    "lang": "en",
                },
            }
        ]
    )
    retriever = Retriever(index, settings, embedder, reranker=Boom())
    hits, timings = retriever.search("backpropagation", k=1, rerank=False)
    assert hits[0].segment_id == "only"
    assert "rerank" in timings


def _cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _index(token: str) -> int:
    from pipeline.sparse import term_index

    return term_index(token)
