"""Research evidence contracts. Declarations do not prove clinical validity."""

import hashlib
import unicodedata
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

Text = Annotated[str, Field(min_length=1)]


def canonical_content(content: str) -> str:
    """NFC Unicode, whitespace collapsed to single ASCII spaces, UTF-8 when hashed."""
    return " ".join(unicodedata.normalize("NFC", content).split())


def content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(canonical_content(content).encode("utf-8")).hexdigest()


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    document_id: Text
    title: Text
    source_type: Literal["synthetic", "repository_authored", "permitted_snippet"]
    source_reference: Text
    publisher_or_origin: Text
    publication_date: date | None = None
    jurisdiction: Text | None = None
    retrieved_at: AwareDatetime | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceDocument(Provenance):
    version: Text | None = None
    content: Text
    content_hash: str = ""

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        canonical = canonical_content(self.content)
        if not canonical:
            raise ValueError("Evidence content must not be empty")
        digest = content_hash(canonical)
        if self.content_hash and self.content_hash != digest:
            raise ValueError("Content hash mismatch")
        object.__setattr__(self, "content", canonical)
        object.__setattr__(self, "content_hash", digest)
        return self


class EvidenceChunk(Provenance):
    chunk_id: Text
    chunk_index: int = Field(ge=0)
    document_version: Text | None = None
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    text: Text
