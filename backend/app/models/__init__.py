"""Register all research persistence models."""

from backend.app.models.clinical_details import (
    Allergy,
    ClinicalNote,
    Condition,
    Medication,
    Observation,
    PatientProfile,
)
from backend.app.models.memory import (
    ClinicalMemoryScope,
    MemoryEntry,
    MemoryEpisode,
    MemoryEvidence,
    MemoryRelationship,
)
from backend.app.models.records import AgentRun, AuditEvent, ClinicalCase, EvidenceRecord

__all__ = [
    "ClinicalMemoryScope",
    "MemoryEntry",
    "MemoryEpisode",
    "MemoryEvidence",
    "MemoryRelationship",
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
