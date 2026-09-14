"""Internal persistence contracts; no public CRUD endpoints."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.app.models.enums import CaseSourceType


class ClinicalCaseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    external_case_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1)
    source_type: CaseSourceType
    deidentified: Literal[True] = True


class ClinicalCaseCreate(ClinicalCaseBase):
    pass


class ClinicalCaseRead(ClinicalCaseBase):
    id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
