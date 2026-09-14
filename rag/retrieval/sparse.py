"""Transparent Okapi BM25, k1=1.5, b=0.75; lowercase alphanumeric tokens."""

import math
import re
from collections import Counter

from rag.ingestion.chunking import corpus_fingerprint
from rag.ingestion.schemas import EvidenceChunk
from rag.retrieval.schemas import RetrievalResult


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class SparseRetriever:
    def __init__(self, chunks: list[EvidenceChunk]):
        self.fingerprint = corpus_fingerprint(chunks)
        self.chunks = sorted(chunks, key=lambda c: c.chunk_id)
        self.terms = [Counter(tokenize(c.title + " " + c.text)) for c in self.chunks]
        self.lengths = [sum(t.values()) for t in self.terms]
        self.average = sum(self.lengths) / len(chunks)
        self.df = Counter(term for row in self.terms for term in row)

    def search(self, query: str, limit: int) -> list[RetrievalResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        scored = []
        for chunk, terms, length in zip(self.chunks, self.terms, self.lengths, strict=True):
            score = 0.0
            for term in sorted(set(tokenize(query))):
                tf = terms[term]
                if tf:
                    idf = math.log(
                        1 + (len(self.chunks) - self.df[term] + 0.5) / (self.df[term] + 0.5)
                    )
                    score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / self.average))
            if score > 0:
                scored.append(RetrievalResult(**chunk.model_dump(), sparse_score=score))
        scored.sort(key=lambda r: (-r.sparse_score, r.chunk_id))
        return [r.model_copy(update={"sparse_rank": i}) for i, r in enumerate(scored[:limit], 1)]
