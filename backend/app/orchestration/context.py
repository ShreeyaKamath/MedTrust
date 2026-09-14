"""Explicit allowlists strip database details and unrelated case fields."""

from backend.app.orchestration.contracts import (
    HistoryContext,
    LabContext,
    MedicationContext,
    Role,
)
from backend.app.schemas.clinical_case import ClinicalCaseCreateRequest, ClinicalCaseDetailResponse


def validate_case(case: ClinicalCaseCreateRequest | ClinicalCaseDetailResponse):
    # Revalidate even already-constructed Pydantic objects; do not trust model_construct/copy.
    data = case.model_dump(mode="json")
    allowed = ClinicalCaseCreateRequest.model_fields
    data = {key: value for key, value in data.items() if key in allowed}
    for key in ("conditions", "observations", "medications", "allergies", "clinical_notes"):
        data[key] = [
            {k: v for k, v in item.items() if k not in {"id", "created_at"}} for item in data[key]
        ]
    if data.get("patient_profile"):
        data["patient_profile"] = {
            k: v
            for k, v in data["patient_profile"].items()
            if k not in {"id", "created_at", "updated_at"}
        }
    return ClinicalCaseCreateRequest.model_validate(data)


def build_context(case: ClinicalCaseCreateRequest, role: Role):
    match role:
        case Role.HISTORY:
            return HistoryContext(
                summary=case.summary, conditions=case.conditions, clinical_notes=case.clinical_notes
            )
        case Role.LAB:
            return LabContext(observations=case.observations)
        case Role.MEDICATION:
            return MedicationContext(medications=case.medications, allergies=case.allergies)
        case _:
            raise ValueError("Specialist context required")
