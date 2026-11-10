from __future__ import annotations

from pipeline.embed import tokenize

RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class LexicalReranker:
    """Token-overlap stand-in used when the cross-encoder weights are not downloaded."""

    model_name = "lexical"

    def score(self, query: str, documents: list[str]) -> list[float]:
        q_tokens = tokenize(query)
        if not q_tokens:
            return [0.0 for _ in documents]
        q_set = set(q_tokens)
        scores = []
        for doc in documents:
            d_tokens = tokenize(doc)
            if not d_tokens:
                scores.append(0.0)
                continue
            overlap = sum(1 for token in d_tokens if token in q_set)
            scores.append(overlap / len(q_set))
        return scores


class CrossEncoderReranker:
    """sentence_transformers CrossEncoder on BAAI/bge-reranker-v2-m3 by default."""

    def __init__(self, model_name: str = RERANKER_MODEL, model=None) -> None:
        self.model_name = model_name
        if model is not None:
            self._model = model
        else:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(model_name)

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        pairs = [(query, doc) for doc in documents]
        raw = self._model.predict(pairs)
        return [float(value) for value in raw]


def build_reranker(backend: str, model_name: str):
    if backend == "cross_encoder":
        return CrossEncoderReranker(model_name or RERANKER_MODEL)
    if backend != "lexical":
        raise ValueError(f"unknown reranker backend {backend}")
    return LexicalReranker()
