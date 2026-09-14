"""Replaceable deterministic lexical reranker; relevance only."""

from rag.retrieval.schemas import RetrievalResult
from rag.retrieval.sparse import tokenize


def rerank(query: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
    terms = set(tokenize(query))

    def score(result: RetrievalResult) -> float:
        title = len(terms & set(tokenize(result.title))) / max(1, len(terms))
        text = len(terms & set(tokenize(result.text))) / max(1, len(terms))
        return result.fusion_score + 0.10 * title + 0.05 * text

    scored = [r.model_copy(update={"rerank_score": score(r)}) for r in results]
    return sorted(scored, key=lambda r: (-r.rerank_score, -r.fusion_score, r.chunk_id))
