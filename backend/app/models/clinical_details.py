"""Simplified clinical research artifacts; no medical inference or EHR authority.

Detail foreign keys RESTRICT case deletion, matching the historical record policy.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, UTCDateTime, utc_now
from backend.app.models.records import IdentityCreatedMixin

if TYPE_CHECKING:
    from backend.app.models.records import ClinicalCase


class CaseDetailMixin(IdentityCreatedMixin):
    clinical_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinical_cases.id", ondelete="RESTRICT"), index=True
    )


class PatientProfile(CaseDetailMixin, Base):
    __tablename__ = "patient_profiles"
    __table_args__ = (
        CheckConstraint("age_years BETWEEN 0 AND 120", name="age_bounds"),
        CheckConstraint("height_cm > 0 AND height_cm <= 300", name="height_bounds"),
        CheckConstraint("weight_kg > 0 AND weight_kg <= 700", name="weight_bounds"),
        CheckConstraint(
            "recorded_sex IN ('female', 'male', 'other', 'unknown')", name="sex_values"
        ),
        CheckConstraint(
            "pregnancy_status IN ('pregnant', 'not_pregnant', 'unknown', 'not_applicable')",
            name="pregnancy_values",
        ),
        CheckConstraint(
            "smoking_status IN ('never', 'former', 'current', 'unknown')", name="smoking_values"
        ),
    )
    clinical_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinical_cases.id", ondelete="RESTRICT"), unique=True
    )
    synthetic_patient_id: Mapped[str] = mapped_column(String(32))
    age_years: Mapped[int | None] = mapped_column(Integer)
    recorded_sex: Mapped[str] = mapped_column(String(16), default="unknown")
    pregnancy_status: Mapped[str | None] = mapped_column(String(16))
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    smoking_status: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now()
    )
    clinical_case: Mapped[ClinicalCase] = relationship(back_populates="patient_profile")


class Condition(CaseDetailMixin, Base):
    __tablename__ = "conditions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'resolved', 'historical', 'unknown')", name="status_values"
        ),
    )
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(64))
    coding_system: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    onset_description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    clinical_case: Mapped[ClinicalCase] = relationship(back_populates="conditions")


class Observation(CaseDetailMixin, Base):
    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint(
            "value_numeric IS NOT NULL OR (value_text IS NOT NULL AND trim(value_text) <> '')",
            name="value_required",
        ),
        CheckConstraint("reference_range_low <= reference_range_high", name="range_order"),
        CheckConstraint(
            "value_numeric IS NULL OR (unit IS NOT NULL AND trim(unit) <> '')",
            name="numeric_unit_required",
        ),
    )
    category: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(64))
    coding_system: Mapped[str | None] = mapped_column(String(128))
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(64))
    reference_range_low: Mapped[float | None] = mapped_column(Float)
    reference_range_high: Mapped[float | None] = mapped_column(Float)
    interpretation: Mapped[str | None] = mapped_column(String(128))
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    clinical_case: Mapped[ClinicalCase] = relationship(back_populates="observations")


class Medication(CaseDetailMixin, Base):
    __tablename__ = "medications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'stopped', 'historical', 'unknown')", name="status_values"
        ),
        CheckConstraint("start_date <= end_date", name="date_order"),
    )
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(64))
    coding_system: Mapped[str | None] = mapped_column(String(128))
    dose: Mapped[str | None] = mapped_column(String(64))
    dose_unit: Mapped[str | None] = mapped_column(String(64))
    route: Mapped[str | None] = mapped_column(String(64))
    frequency: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    clinical_case: Mapped[ClinicalCase] = relationship(back_populates="medications")


class Allergy(CaseDetailMixin, Base):
    __tablename__ = "allergies"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive', 'unknown')", name="status_values"),
        CheckConstraint(
            "severity IN ('mild', 'moderate', 'severe', 'unknown')", name="severity_values"
        ),
    )
    substance: Mapped[str] = mapped_column(String(255))
    reaction: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    recorded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    clinical_case: Mapped[ClinicalCase] = relationship(back_populates="allergies")


class ClinicalNote(CaseDetailMixin, Base):
    """Untrusted narrative input for future agents; never private chain-of-thought."""

    __tablename__ = "clinical_notes"
    note_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    authored_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    clinical_case: Mapped[ClinicalCase] = relationship(back_populates="clinical_notes")
