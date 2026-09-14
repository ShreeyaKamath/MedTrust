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

    agent_runtime: Literal["mock", "openclaw"] = "mock"
    openclaw_timeout_seconds: int = Field(default=60, ge=1, le=600)
    openclaw_history_agent: str = Field(
        default="medtrust-history", pattern=r"^medtrust-[a-z][a-z0-9-]{0,63}$"
    )
    openclaw_lab_agent: str = Field(
        default="medtrust-lab", pattern=r"^medtrust-[a-z][a-z0-9-]{0,63}$"
    )
    openclaw_medication_agent: str = Field(
        default="medtrust-medication", pattern=r"^medtrust-[a-z][a-z0-9-]{0,63}$"
    )
    openclaw_evidence_agent: str = Field(
        default="medtrust-evidence", pattern=r"^medtrust-[a-z][a-z0-9-]{0,63}$"
    )
    openclaw_critic_agent: str = Field(
        default="medtrust-critic", pattern=r"^medtrust-[a-z][a-z0-9-]{0,63}$"
    )
    openclaw_coordinator_agent: str = Field(
        default="medtrust-coordinator", pattern=r"^medtrust-[a-z][a-z0-9-]{0,63}$"
    )

    env: Environment = "development"
    api_host: str = Field(default="127.0.0.1", min_length=1)
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
