"""Structured rankings retain the complete source payload."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rag.ingestion.schemas import EvidenceChunk


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=100, strict=True)
    mode: Literal["dense", "sparse", "hybrid"] = "hybrid"


class RetrievalResult(EvidenceChunk):
    dense_score: float | None = None
    sparse_score: float | None = None
    dense_rank: int | None = Field(default=None, ge=1)
    sparse_rank: int | None = Field(default=None, ge=1)
    fusion_score: float = 0.0
    rerank_score: float = 0.0
    final_rank: int = Field(default=0, ge=0)
