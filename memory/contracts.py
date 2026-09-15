"""Canonical, bounded Phase 7 contracts, independent of agent and ORM contracts."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Score = Annotated[float, Field(ge=0, le=1, strict=True)]


class MemoryContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", from_attributes=True, allow_inf_nan=False, revalidate_instances="always"
    )


class EntryType(StrEnum):
    SOURCE_FACT = "source_fact"
    DERIVED_ASSERTION = "derived_assertion"


class RelationType(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    CORRECTS = "corrects"


class SourceKind(StrEnum):
    CASE = "clinical_case"
    PROFILE = "patient_profile"
    CONDITION = "condition"
    OBSERVATION = "observation"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    NOTE = "clinical_note"


class EventTime(MemoryContract):
    precision: Literal["unknown", "date", "datetime"] = "unknown"
    date_value: date | None = None
    datetime_value: AwareDatetime | None = None

    @model_validator(mode="after")
    def precision_matches(self):
        if not (
            (
                self.precision == "unknown"
                and self.date_value is None
                and self.datetime_value is None
            )
            or (
                self.precision == "date"
                and self.date_value is not None
                and self.datetime_value is None
            )
            or (
                self.precision == "datetime"
                and self.date_value is None
                and self.datetime_value is not None
            )
        ):
            raise ValueError("Event precision and value disagree")
        return self


class SourceReference(MemoryContract):
    kind: SourceKind
    record_id: UUID
    field: str = Field(min_length=1, max_length=64)


class SourceSnapshot(MemoryContract):
    canonicalization: Literal["memory-json-v1"] = "memory-json-v1"
    case_id: UUID
    reference: SourceReference
    source_type: Literal["synthetic", "deidentified"]
    value: JsonValue
    semantic_identity: dict[str, JsonValue]
    event: EventTime
    source_received_at: AwareDatetime
    digest: Digest

    @model_validator(mode="after")
    def verify_digest(self):
        from memory.provenance import structured_digest

        if structured_digest(self.model_dump(exclude={"digest"})) != self.digest:
            raise ValueError("Snapshot digest mismatch")
        return self


class ConfidenceComponents(MemoryContract):
    """Observable heuristics, not probabilities of clinical correctness or agent trust."""

    source_quality: Score
    provenance_completeness: Score
    freshness: Score
    temporal_reliability: Score
    consistency: Score


class SelectionRequest(MemoryContract):
    scope_id: UUID
    case_id: UUID
    as_of: AwareDatetime
    max_entries: int = Field(default=20, ge=1, le=100, strict=True)
    max_characters: int = Field(default=20000, ge=1024, le=100000, strict=True)
    freshness_days: int = Field(default=365, ge=1, le=36500, strict=True)


class MemoryItem(MemoryContract):
    id: UUID
    case_id: UUID
    entry_type: EntryType
    source_kind: SourceKind | None
    field: str | None
    value: JsonValue
    event: EventTime
    available_at: AwareDatetime
    digest: Digest
    producing_role: str | None = None
    source_ids: list[UUID] = Field(default_factory=list, max_length=300)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=50)
    conflicts: list[UUID] = Field(default_factory=list, max_length=100)
    conflicts_omitted_count: int = Field(default=0, ge=0)
    components: ConfidenceComponents
    authoritative: Literal[False] = False


class MemorySelection(MemoryContract):
    scope_id: UUID
    as_of: AwareDatetime
    entries: list[MemoryItem] = Field(default_factory=list, max_length=100)
    omitted_count: int = Field(default=0, ge=0)
    excluded_count: int = Field(default=0, ge=0)
    characters: int = Field(default=0, ge=0)
    untrusted: Literal[True] = True
