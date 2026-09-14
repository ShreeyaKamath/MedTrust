"""Internal persistence contracts; no public CRUD endpoints."""

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class EvidenceRecordBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    clinical_case_id: UUID | None = None
    source_type: str = Field(min_length=1, max_length=64)
    source_title: str = Field(min_length=1, max_length=255)
    source_reference: str = Field(min_length=1)
    publisher_or_origin: str | None = Field(default=None, max_length=255)
    publication_date: date | None = None
    retrieved_at: AwareDatetime
    content_hash: str = Field(min_length=1, max_length=255)
    provenance_metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecordCreate(EvidenceRecordBase):
    pass


class EvidenceRecordRead(EvidenceRecordBase):
    id: UUID
    created_at: AwareDatetime
