"""Application-preserved research memory history, with explicit episode membership."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime
from backend.app.models.records import IdentityCreatedMixin


class ClinicalMemoryScope(IdentityCreatedMixin, Base):
    __tablename__ = "clinical_memory_scopes"
    research_id: Mapped[str] = mapped_column(String(64), unique=True)


class MemoryEpisode(IdentityCreatedMixin, Base):
    __tablename__ = "memory_episodes"
    __table_args__ = (UniqueConstraint("scope_id", "clinical_case_id"),)
    scope_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinical_memory_scopes.id", ondelete="RESTRICT"), index=True
    )
    clinical_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinical_cases.id", ondelete="RESTRICT"), unique=True
    )


class MemoryEntry(IdentityCreatedMixin, Base):
    __tablename__ = "memory_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["scope_id", "clinical_case_id"],
            ["memory_episodes.scope_id", "memory_episodes.clinical_case_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("scope_id", "identity_digest"),
        CheckConstraint(
            "entry_type IN ('source_fact', 'derived_assertion')", name="entry_type_values"
        ),
        CheckConstraint(
            "(entry_type = 'source_fact' AND source_record_id IS NOT NULL AND "
            "source_kind IS NOT NULL AND source_field IS NOT NULL AND producing_run_id "
            "IS NULL) OR (entry_type = 'derived_assertion' AND producing_run_id IS NOT "
            "NULL AND source_record_id IS NULL AND source_kind IS NULL AND source_field "
            "IS NULL)",
            name="origin_required",
        ),
        CheckConstraint(
            "source_kind IS NULL OR source_kind IN ('clinical_case', 'patient_profile', "
            "'condition', 'observation', 'medication', 'allergy', 'clinical_note')",
            name="source_kind_values",
        ),
    )
    scope_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinical_memory_scopes.id", ondelete="RESTRICT"), index=True
    )
    clinical_case_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    entry_type: Mapped[str] = mapped_column(String(32))
    source_record_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_kind: Mapped[str | None] = mapped_column(String(32))
    source_field: Mapped[str | None] = mapped_column(String(64))
    producing_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), index=True
    )
    producing_role: Mapped[str | None] = mapped_column(String(128))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON(none_as_null=True))
    snapshot_digest: Mapped[str] = mapped_column(String(71))
    identity_digest: Mapped[str] = mapped_column(String(71))
    event: Mapped[dict[str, Any]] = mapped_column(JSON(none_as_null=True))
    available_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


class MemoryRelationship(IdentityCreatedMixin, Base):
    __tablename__ = "memory_relationships"
    __table_args__ = (
        UniqueConstraint("from_entry_id", "to_entry_id", "relation_type"),
        CheckConstraint("from_entry_id <> to_entry_id", name="not_self"),
        CheckConstraint(
            "relation_type IN ('supports', 'contradicts', 'supersedes', 'corrects')",
            name="relation_type_values",
        ),
    )
    scope_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinical_memory_scopes.id", ondelete="RESTRICT"), index=True
    )
    from_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_entries.id", ondelete="RESTRICT"), index=True
    )
    to_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_entries.id", ondelete="RESTRICT"), index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32))
    available_at: Mapped[datetime] = mapped_column(UTCDateTime())


class MemoryEvidence(IdentityCreatedMixin, Base):
    __tablename__ = "memory_evidence"
    __table_args__ = (UniqueConstraint("entry_id", "identity_digest"),)
    entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_entries.id", ondelete="RESTRICT"), index=True
    )
    evidence_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="RESTRICT"), index=True
    )
    identity_digest: Mapped[str] = mapped_column(String(71))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON(none_as_null=True))
