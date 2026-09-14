"""Register all research persistence models."""

from backend.app.models.clinical_details import (
    Allergy,
    ClinicalNote,
    Condition,
    Medication,
    Observation,
    PatientProfile,
)
from backend.app.models.records import AgentRun, AuditEvent, ClinicalCase, EvidenceRecord

__all__ = [
    "AgentRun",
    "AuditEvent",
    "ClinicalCase",
    "EvidenceRecord",
    "Allergy",
    "ClinicalNote",
    "Condition",
    "Medication",
    "Observation",
    "PatientProfile",
]
