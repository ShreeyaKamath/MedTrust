"""Reciprocal rank fusion uses one-based ranks, never clinical confidence."""

from rag.retrieval.schemas import RetrievalResult


def fuse(
    dense: list[RetrievalResult], sparse: list[RetrievalResult], constant: int = 60
) -> list[RetrievalResult]:
    if constant < 1:
        raise ValueError("RRF constant must be positive")
    merged: dict[str, RetrievalResult] = {}
    for kind, results in [("dense", dense), ("sparse", sparse)]:
        seen = set()
        for result in results:
            if result.chunk_id in seen:
                continue
            seen.add(result.chunk_id)
            rank = len(seen)
            previous = merged.get(result.chunk_id, result)
            merged[result.chunk_id] = previous.model_copy(
                update={
                    f"{kind}_rank": rank,
                    f"{kind}_score": getattr(result, f"{kind}_score"),
                    "fusion_score": (previous.fusion_score if result.chunk_id in merged else 0)
                    + 1 / (constant + rank),
                }
            )
    return sorted(merged.values(), key=lambda r: (-r.fusion_score, r.chunk_id))
