"""Deterministic novelty floor: bag-of-words cosine geometry.

The published creativity metrics upgrade to neural embeddings; this BOW
layer is the token-free deterministic floor (and the regression test for
the geometry). Both metrics follow their sources: consensus_distance =
distance from the cross-model centroid; iteration novelty = 1 - max
cosine similarity to all prior answers (AidanBench).
"""

from __future__ import annotations

import math
import re
from collections import Counter

_WORDS = re.compile(r"[a-z0-9']+")


def bow_vector(text: str) -> dict[str, float]:
    return dict(Counter(_WORDS.findall(text.lower())))


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(key, 0.0) for key, value in a.items())
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def centroid(vectors: tuple[dict[str, float], ...]) -> dict[str, float]:
    if not vectors:
        return {}
    summed: dict[str, float] = {}
    for vector in vectors:
        for key, value in vector.items():
            summed[key] = summed.get(key, 0.0) + value
    return {key: value / len(vectors) for key, value in summed.items()}


def centroid_distance(text: str, panel_texts: tuple[str, ...]) -> float:
    """consensus_distance: 1 - cosine(answer, centroid of the whole panel)."""

    return 1.0 - cosine(bow_vector(text), centroid(tuple(bow_vector(t) for t in panel_texts)))


def iteration_novelty(answers: tuple[str, ...]) -> tuple[float, ...]:
    """Per-answer novelty = 1 - max cosine to all PRIOR answers; the first
    answer scores 1.0 by convention."""

    vectors = tuple(bow_vector(a) for a in answers)
    scores: list[float] = []
    for i, vector in enumerate(vectors):
        if i == 0:
            scores.append(1.0)
            continue
        max_sim = max(cosine(vector, prior) for prior in vectors[:i])
        scores.append(1.0 - max_sim)
    return tuple(scores)
