from __future__ import annotations

import hashlib
import math
import re


class DeterministicEmbeddingFunction:
    """Small offline embedding function for reproducible local/demo retrieval."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def __call__(self, input):  # Chroma calls this argument `input`.
        if isinstance(input, str):
            input = [input]
        return [self.embed(text) for text in input]

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    denom = (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1.0
    return sum(x * y for x, y in zip(a, b)) / denom
