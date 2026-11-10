from __future__ import annotations

import hashlib
import math
import re

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


class HashEmbedder:
    """Feature-hashing embedder. Shared tokens raise cosine similarity.

    This is the offline default so tests and CPU demos do not download BGE.
    Set EMBEDDING_BACKEND=sentence_transformers for BAAI/bge-m3.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.model_name = f"hash-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text, self.dim) for text in texts]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, dim: int) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        out = []
        for vector in vectors:
            values = [float(v) for v in vector]
            if len(values) != self.dim:
                raise ValueError(
                    f"{self.model_name} produced dim {len(values)}, EMBEDDING_DIM is {self.dim}"
                )
            out.append(values)
        return out


def build_embedder(backend: str, model_name: str, dim: int):
    if backend == "sentence_transformers":
        return SentenceTransformerEmbedder(model_name, dim)
    if backend != "hash":
        raise ValueError(f"unknown embedding backend {backend}")
    return HashEmbedder(dim)


def _hash_vector(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    tokens = tokenize(text)
    if not tokens:
        vec[0] = 1.0
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[index] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        vec[0] = 1.0
        return vec
    return [v / norm for v in vec]
