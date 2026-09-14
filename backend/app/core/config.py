"""Typed infrastructure settings; future service variables are intentionally ignored."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEDTRUST_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: SecretStr = Field(default=SecretStr(""), validation_alias="DATABASE_URL")

    qdrant_url: str = Field(default="http://127.0.0.1:6333", validation_alias="QDRANT_URL")
    qdrant_collection: str = Field(
        default="medtrust_evidence_v1", min_length=1, validation_alias="QDRANT_COLLECTION"
    )
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", min_length=1)
    embedding_revision: str | None = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
    rag_chunk_size: int = Field(default=80, ge=1)
    rag_chunk_overlap: int = Field(default=16, ge=0)
    rag_top_k: int = Field(default=5, ge=1, le=100)
    rag_rrf_constant: int = Field(default=60, ge=1)

    @model_validator(mode="after")
    def validate_chunk_settings(self):
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size")
        return self

    env: Environment = "development"
    api_host: str = Field(default="127.0.0.1", min_length=1)
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
