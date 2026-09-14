"""FHIR-inspired application schemas, not FHIR resources or de-identification software."""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=255)]
Code = Annotated[str, Field(min_length=1, max_length=64)]
Label = Annotated[str, Field(min_length=1, max_length=128)]
Narrative = Annotated[str, Field(min_length=1, max_length=20000)]


class ResearchInput(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )


class DetailRead(ResearchInput):
    id: UUID
    created_at: AwareDatetime


class PatientProfileCreate(ResearchInput):
    synthetic_patient_id: str = Field(pattern=r"^SYN-P[0-9]{3,12}$", max_length=32)
    age_years: int | None = Field(default=None, ge=0, le=120, strict=True)
    recorded_sex: Literal["female", "male", "other", "unknown"] = "unknown"
    pregnancy_status: Literal["pregnant", "not_pregnant", "unknown", "not_applicable"] | None = None
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=700)
    smoking_status: Literal["never", "former", "current", "unknown"] | None = None


class PatientProfileRead(PatientProfileCreate, DetailRead):
    updated_at: AwareDatetime


class ConditionCreate(ResearchInput):
    name: ShortText
    code: Code | None = None
    coding_system: Label | None = None
    status: Literal["active", "resolved", "historical", "unknown"] = "unknown"
    onset_description: Narrative | None = None
    notes: Narrative | None = None


class ConditionRead(ConditionCreate, DetailRead):
    pass


class ObservationCreate(ResearchInput):
    category: Code
    name: ShortText
    code: Code | None = None
    coding_system: Label | None = None
    value_numeric: float | None = None
    value_text: Narrative | None = None
    unit: Code | None = None
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    interpretation: Label | None = Field(
        default=None, description="Supplied label; never inferred."
    )
    observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_value(self) -> Self:
        if self.value_numeric is None and self.value_text is None:
            raise ValueError("An observation value is required")
        if self.value_numeric is not None and self.unit is None:
            raise ValueError(
                "Numeric observations require an explicit unit; use '1' if dimensionless"
            )
        if (
            self.reference_range_low is not None
            and self.reference_range_high is not None
            and self.reference_range_low > self.reference_range_high
        ):
            raise ValueError("Reference range bounds must be ordered")
        return self


class ObservationRead(ObservationCreate, DetailRead):
    pass


class MedicationCreate(ResearchInput):
    name: ShortText
    code: Code | None = None
    coding_system: Label | None = None
    dose: Code | None = None
    dose_unit: Code | None = None
    route: Code | None = None
    frequency: Label | None = None
    status: Literal["active", "stopped", "historical", "unknown"] = "unknown"
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Medication dates must be ordered")
        return self


class MedicationRead(MedicationCreate, DetailRead):
    pass


class AllergyCreate(ResearchInput):
    substance: ShortText
    reaction: Narrative | None = None
    severity: Literal["mild", "moderate", "severe", "unknown"] | None = None
    status: Literal["active", "inactive", "unknown"] = "unknown"
    recorded_at: AwareDatetime | None = None


class AllergyRead(AllergyCreate, DetailRead):
    pass


class ClinicalNoteCreate(ResearchInput):
    note_type: Code
    title: ShortText | None = None
    content: Narrative = Field(
        description="Untrusted research narrative; no identifiers or private reasoning."
    )
    authored_at: AwareDatetime | None = None
    synthetic: bool = Field(default=True, strict=True)


class ClinicalNoteRead(ClinicalNoteCreate, DetailRead):
    pass
