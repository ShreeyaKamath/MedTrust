"""Exploratory document relevance benchmark, not clinical correctness labels."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from rag.evaluation.metrics import mean_reciprocal_rank, ndcg_at_k, recall_at_k, unique
from rag.retrieval.service import RetrievalService

QUERIES = Path(__file__).resolve().parents[2] / "datasets/synthetic/evidence_queries.json"


class BenchmarkQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=2000)
    relevant_document_ids: set[str] = Field(min_length=1)


def load_queries(document_ids: set[str], path: Path = QUERIES) -> list[BenchmarkQuery]:
    queries = TypeAdapter(list[BenchmarkQuery]).validate_json(path.read_text(encoding="utf-8"))
    if len(queries) < 20 or len({q.query_id for q in queries}) != len(queries):
        raise ValueError("Benchmark requires at least 20 unique query IDs")
    if any(not q.relevant_document_ids <= document_ids for q in queries):
        raise ValueError("Unknown relevant document ID")
    return queries


def evaluate(
    service: RetrievalService,
    queries: list[BenchmarkQuery],
    modes: tuple[str, ...] = ("sparse", "dense", "hybrid", "hybrid+rerank"),
) -> dict:
    if not queries:
        raise ValueError("Benchmark must not be empty")
    output = {}
    for mode in modes:
        if mode not in {"sparse", "dense", "hybrid", "hybrid+rerank"}:
            raise ValueError("Unknown evaluation mode")
        rankings = [
            unique(
                [
                    r.document_id
                    for r in service.retrieve_evidence(
                        q.query, top_k=100, mode=mode.split("+")[0], reranking="+" in mode
                    )
                ]
            )
            for q in queries
        ]
        labels = [q.relevant_document_ids for q in queries]
        metrics = {
            f"Recall@{k}": sum(recall_at_k(r, y, k) for r, y in zip(rankings, labels, strict=True))
            / len(queries)
            for k in (1, 3, 5)
        }
        metrics["MRR"] = mean_reciprocal_rank(rankings, labels)
        metrics["nDCG@5"] = sum(
            ndcg_at_k(r, y, 5) for r, y in zip(rankings, labels, strict=True)
        ) / len(queries)
        output[mode] = {"query_count": len(queries), **metrics}
    return output
