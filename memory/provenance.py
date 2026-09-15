"""Host-owned clinical field mapping and structured snapshot canonicalization."""

import hashlib
import json
import unicodedata
from datetime import UTC, date, datetime
from uuid import UUID

from backend.app.models.clinical_details import (
    Allergy,
    ClinicalNote,
    Condition,
    Medication,
    Observation,
    PatientProfile,
)
from backend.app.models.records import ClinicalCase
from backend.app.schemas.clinical_details import (
    AllergyCreate,
    ClinicalNoteCreate,
    ConditionCreate,
    MedicationCreate,
    ObservationCreate,
)
from memory.contracts import EventTime, SourceKind, SourceReference, SourceSnapshot

SOURCE_MODELS = {
    SourceKind.CASE: ClinicalCase,
    SourceKind.PROFILE: PatientProfile,
    SourceKind.CONDITION: Condition,
    SourceKind.OBSERVATION: Observation,
    SourceKind.MEDICATION: Medication,
    SourceKind.ALLERGY: Allergy,
    SourceKind.NOTE: ClinicalNote,
}
# Profile identifiers and demographics are deliberately not memory fields in Phase 7.
SOURCE_FIELDS = {
    SourceKind.CASE: {"summary"},
    SourceKind.PROFILE: set(),
    SourceKind.CONDITION: set(ConditionCreate.model_fields),
    SourceKind.OBSERVATION: set(ObservationCreate.model_fields),
    SourceKind.MEDICATION: set(MedicationCreate.model_fields),
    SourceKind.ALLERGY: set(AllergyCreate.model_fields),
    SourceKind.NOTE: set(ClinicalNoteCreate.model_fields) - {"synthetic"},
}


def normalize(value):
    """NFC strings (whitespace preserved), UTC instants, ISO dates, sorted JSON keys."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone required")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (date, UUID)):
        return str(value)
    if isinstance(value, dict):
        result = {normalize(k): normalize(v) for k, v in value.items()}
        if len(result) != len(value):
            raise ValueError("Canonical key collision")
        return result
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    return value


def canonical_json(value) -> str:
    return json.dumps(
        normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def structured_digest(value) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def event_time(record, kind: SourceKind) -> EventTime:
    field = {
        SourceKind.OBSERVATION: "observed_at",
        SourceKind.NOTE: "authored_at",
        SourceKind.ALLERGY: "recorded_at",
    }.get(kind)
    value = getattr(record, field, None) if field else None
    if value is not None:
        return EventTime(precision="datetime", datetime_value=value)
    if kind == SourceKind.MEDICATION:
        value = record.end_date if record.status == "stopped" else record.start_date
        if value is not None:
            return EventTime(precision="date", date_value=value)
    return EventTime()


def snapshot(record, case: ClinicalCase, reference: SourceReference) -> SourceSnapshot:
    if reference.field not in SOURCE_FIELDS[reference.kind]:
        raise ValueError("invalid_source_field")
    identity = {}
    if reference.kind == SourceKind.OBSERVATION:
        identity = {
            k: getattr(record, k) for k in ("category", "name", "code", "coding_system", "unit")
        }
    data = dict(
        canonicalization="memory-json-v1",
        case_id=case.id,
        reference=reference.model_dump(),
        source_type=case.source_type,
        value=getattr(record, reference.field),
        semantic_identity=identity,
        event=event_time(record, reference.kind).model_dump(),
        source_received_at=record.created_at,
    )
    return SourceSnapshot.model_validate(normalize(data) | {"digest": structured_digest(data)})
