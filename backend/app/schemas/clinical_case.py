"""Research case metadata and nested ingestion contracts."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.app.models.enums import CaseSourceType
from backend.app.schemas.clinical_details import (
    AllergyCreate,
    AllergyRead,
    ClinicalNoteCreate,
    ClinicalNoteRead,
    ConditionCreate,
    ConditionRead,
    MedicationCreate,
    MedicationRead,
    ObservationCreate,
    ObservationRead,
    PatientProfileCreate,
    PatientProfileRead,
)


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


class ClinicalCaseCreateRequest(ClinicalCaseBase):
    """Only synthetic or explicitly de-identified research input is eligible."""

    model_config = ConfigDict(str_strip_whitespace=True)
    deidentified: Literal[True]
    summary: str = Field(min_length=1, max_length=20000)
    patient_profile: PatientProfileCreate | None = None
    conditions: list[ConditionCreate] = Field(default_factory=list, max_length=100)
    observations: list[ObservationCreate] = Field(default_factory=list, max_length=100)
    medications: list[MedicationCreate] = Field(default_factory=list, max_length=100)
    allergies: list[AllergyCreate] = Field(default_factory=list, max_length=100)
    clinical_notes: list[ClinicalNoteCreate] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_note_eligibility(self) -> Self:
        if self.source_type == CaseSourceType.SYNTHETIC and any(
            not note.synthetic for note in self.clinical_notes
        ):
            raise ValueError("Synthetic cases require synthetic notes")
        return self


class ClinicalCaseDetailResponse(ClinicalCaseRead):
    patient_profile: PatientProfileRead | None = None
    conditions: list[ConditionRead]
    observations: list[ObservationRead]
    medications: list[MedicationRead]
    allergies: list[AllergyRead]
    clinical_notes: list[ClinicalNoteRead]
