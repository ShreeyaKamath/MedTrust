"""Independent evidence search; missing dense infrastructure fails explicitly."""

from typing import Protocol

from rag.reranking.lexical import rerank
from rag.retrieval.hybrid import fuse
from rag.retrieval.schemas import RetrievalResult, SearchRequest
from rag.retrieval.sparse import SparseRetriever


class DenseSearch(Protocol):
    fingerprint: str

    def search(self, query: str, limit: int) -> list[RetrievalResult]: ...


class RetrievalService:
    def __init__(
        self,
        sparse: SparseRetriever,
        dense: DenseSearch | None = None,
        fusion_constant: int = 60,
        candidate_limit: int = 100,
    ):
        if dense is not None and dense.fingerprint != sparse.fingerprint:
            raise ValueError("Dense and sparse must use the same corpus")
        if fusion_constant < 1 or candidate_limit < 1:
            raise ValueError("Ranking constants must be positive")
        self.sparse, self.dense = sparse, dense
        self.fusion_constant, self.candidate_limit = fusion_constant, candidate_limit

    def retrieve_evidence(
        self, query: str, top_k: int = 5, mode: str = "hybrid", reranking: bool = False
    ) -> list[RetrievalResult]:
        request = SearchRequest(query=query, top_k=top_k, mode=mode)
        if reranking and mode != "hybrid":
            raise ValueError("Reranking is defined for hybrid mode only")
        limit = max(top_k, self.candidate_limit)
        dense, sparse = [], []
        if mode != "sparse":
            if self.dense is None:
                raise RuntimeError("Dense retrieval unavailable; select sparse mode explicitly")
            dense = self.dense.search(request.query, limit)
        if mode != "dense":
            sparse = self.sparse.search(request.query, limit)
        results = fuse(dense, sparse, self.fusion_constant)
        if reranking:
            results = rerank(request.query, results)
        return [r.model_copy(update={"final_rank": i}) for i, r in enumerate(results[:top_k], 1)]
