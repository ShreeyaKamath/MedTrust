"""Research artifacts only, never authoritative EHR records or hidden reasoning.

Foreign keys RESTRICT deletion. passive_deletes='all' prevents ORM nulling of
optional references on parent deletion, including loaded collections. No delete
cascades: historical runs, evidence and audit links must not disappear silently.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, UTCDateTime, utc_now
from backend.app.models.enums import AgentRunStatus, AuditOutcome, CaseSourceType, enum_column


class IdentityCreatedMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )


class ClinicalCase(IdentityCreatedMixin, Base):
    __tablename__ = "clinical_cases"
    __table_args__ = (CheckConstraint("deidentified = true", name="deidentified_only"),)
    external_case_id: Mapped[str] = mapped_column(String(128), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    source_type: Mapped[CaseSourceType] = mapped_column(
        enum_column(CaseSourceType, "case_source_type")
    )
    deidentified: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now()
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="clinical_case", passive_deletes="all"
    )
    evidence_records: Mapped[list[EvidenceRecord]] = relationship(
        back_populates="clinical_case", passive_deletes="all"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="clinical_case", passive_deletes="all"
    )


class AgentRun(IdentityCreatedMixin, Base):
    __tablename__ = "agent_runs"
    clinical_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinical_cases.id", ondelete="RESTRICT"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(128))
    agent_role: Mapped[str] = mapped_column(String(128))
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column(AgentRunStatus, "agent_run_status"), default=AgentRunStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    model_provider: Mapped[str | None] = mapped_column(String(128))
    model_name: Mapped[str | None] = mapped_column(String(255))
    input_reference: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    clinical_case: Mapped[ClinicalCase] = relationship(back_populates="agent_runs")
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="agent_run", passive_deletes="all"
    )


class EvidenceRecord(IdentityCreatedMixin, Base):
    """Metadata only. Optional case allows a shared, case-independent source."""

    __tablename__ = "evidence_records"
    clinical_case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clinical_cases.id", ondelete="RESTRICT"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(64))
    source_title: Mapped[str] = mapped_column(String(255))
    source_reference: Mapped[str] = mapped_column(Text)
    publisher_or_origin: Mapped[str | None] = mapped_column(String(255))
    publication_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    content_hash: Mapped[str] = mapped_column(String(255))
    provenance_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON(none_as_null=True), default=dict
    )
    clinical_case: Mapped[ClinicalCase | None] = relationship(back_populates="evidence_records")


class AuditEvent(IdentityCreatedMixin, Base):
    """Append-only by convention; database immutability enforcement is deferred.

    details must contain safe structured metadata only: no secrets, API keys,
    OAuth tokens, sensitive records/full prompts, or hidden chain-of-thought.
    These restrictions also apply to every free-text/JSON field in this module.
    """

    __tablename__ = "audit_events"
    clinical_case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clinical_cases.id", ondelete="RESTRICT"), index=True
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(128))
    actor_type: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str | None] = mapped_column(String(128))
    resource_id: Mapped[str | None] = mapped_column(String(128))
    outcome: Mapped[AuditOutcome] = mapped_column(enum_column(AuditOutcome, "audit_outcome"))
    details: Mapped[dict[str, Any]] = mapped_column(JSON(none_as_null=True), default=dict)
    clinical_case: Mapped[ClinicalCase | None] = relationship(back_populates="audit_events")
    agent_run: Mapped[AgentRun | None] = relationship(back_populates="audit_events")
