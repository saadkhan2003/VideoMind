from __future__ import annotations

import zlib
from collections import Counter

from pipeline.embed import tokenize


def term_index(token: str) -> int:
    return zlib.crc32(token.encode()) & 0x7FFFFFFF


def sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """Term frequencies keyed by a stable hash. Qdrant applies the IDF modifier."""
    counts = Counter(tokenize(text))
    if not counts:
        return [0], [1e-6]
    items = sorted((term_index(token), float(count)) for token, count in counts.items())
    # Merge the rare hash collision by summing weights.
    merged: dict[int, float] = {}
    for index, weight in items:
        merged[index] = merged.get(index, 0.0) + weight
    indices = sorted(merged)
    return indices, [merged[i] for i in indices]
