"""Binary relevance metrics; duplicate IDs earn no additional credit."""

import math
from collections.abc import Sequence


def unique(ranking: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(ranking))


def _validate(relevant: set[str], k: int = 1) -> None:
    if not relevant or k < 1:
        raise ValueError("Metrics require nonempty relevance labels and positive K")


def recall_at_k(ranking: Sequence[str], relevant: set[str], k: int) -> float:
    _validate(relevant, k)
    return len(set(unique(ranking)[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranking: Sequence[str], relevant: set[str]) -> float:
    _validate(relevant)
    return next((1 / i for i, item in enumerate(unique(ranking), 1) if item in relevant), 0.0)


def mean_reciprocal_rank(rankings: Sequence[Sequence[str]], labels: Sequence[set[str]]) -> float:
    if not rankings or len(rankings) != len(labels):
        raise ValueError("MRR requires paired nonempty rankings and labels")
    return sum(reciprocal_rank(r, y) for r, y in zip(rankings, labels, strict=True)) / len(labels)


def ndcg_at_k(ranking: Sequence[str], relevant: set[str], k: int) -> float:
    _validate(relevant, k)
    dcg = sum(
        1 / math.log2(i + 1) for i, item in enumerate(unique(ranking)[:k], 1) if item in relevant
    )
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(relevant)) + 1))
    return dcg / ideal
