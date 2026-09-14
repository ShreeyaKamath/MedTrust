"""Simplified clinical research case details.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "allergies",
        sa.Column("substance", sa.String(length=255), nullable=False),
        sa.Column("reaction", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinical_case_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "severity IN ('mild', 'moderate', 'severe', 'unknown')",
            name=op.f("ck_allergies_severity_values"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'unknown')", name=op.f("ck_allergies_status_values")
        ),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_allergies_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allergies")),
    )
    op.create_index(
        op.f("ix_allergies_clinical_case_id"), "allergies", ["clinical_case_id"], unique=False
    )
    op.create_table(
        "clinical_notes",
        sa.Column("note_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synthetic", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("clinical_case_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_clinical_notes_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinical_notes")),
    )
    op.create_index(
        op.f("ix_clinical_notes_clinical_case_id"),
        "clinical_notes",
        ["clinical_case_id"],
        unique=False,
    )
    op.create_table(
        "conditions",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("coding_system", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("onset_description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("clinical_case_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active', 'resolved', 'historical', 'unknown')",
            name=op.f("ck_conditions_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_conditions_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conditions")),
    )
    op.create_index(
        op.f("ix_conditions_clinical_case_id"), "conditions", ["clinical_case_id"], unique=False
    )
    op.create_table(
        "medications",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("coding_system", sa.String(length=128), nullable=True),
        sa.Column("dose", sa.String(length=64), nullable=True),
        sa.Column("dose_unit", sa.String(length=64), nullable=True),
        sa.Column("route", sa.String(length=64), nullable=True),
        sa.Column("frequency", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("clinical_case_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active', 'stopped', 'historical', 'unknown')",
            name=op.f("ck_medications_status_values"),
        ),
        sa.CheckConstraint("start_date <= end_date", name=op.f("ck_medications_date_order")),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_medications_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medications")),
    )
    op.create_index(
        op.f("ix_medications_clinical_case_id"), "medications", ["clinical_case_id"], unique=False
    )
    op.create_table(
        "observations",
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("coding_system", sa.String(length=128), nullable=True),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("reference_range_low", sa.Float(), nullable=True),
        sa.Column("reference_range_high", sa.Float(), nullable=True),
        sa.Column("interpretation", sa.String(length=128), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinical_case_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "value_numeric IS NOT NULL OR (value_text IS NOT NULL AND trim(value_text) <> '')",
            name=op.f("ck_observations_value_required"),
        ),
        sa.CheckConstraint(
            "value_numeric IS NULL OR (unit IS NOT NULL AND trim(unit) <> '')",
            name=op.f("ck_observations_numeric_unit_required"),
        ),
        sa.CheckConstraint(
            "reference_range_low <= reference_range_high", name=op.f("ck_observations_range_order")
        ),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_observations_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_observations")),
    )
    op.create_index(
        op.f("ix_observations_clinical_case_id"), "observations", ["clinical_case_id"], unique=False
    )
    op.create_table(
        "patient_profiles",
        sa.Column("clinical_case_id", sa.Uuid(), nullable=False),
        sa.Column("synthetic_patient_id", sa.String(length=32), nullable=False),
        sa.Column("age_years", sa.Integer(), nullable=True),
        sa.Column("recorded_sex", sa.String(length=16), nullable=False),
        sa.Column("pregnancy_status", sa.String(length=16), nullable=True),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("smoking_status", sa.String(length=16), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "pregnancy_status IN ('pregnant', 'not_pregnant', 'unknown', 'not_applicable')",
            name=op.f("ck_patient_profiles_pregnancy_values"),
        ),
        sa.CheckConstraint(
            "recorded_sex IN ('female', 'male', 'other', 'unknown')",
            name=op.f("ck_patient_profiles_sex_values"),
        ),
        sa.CheckConstraint(
            "smoking_status IN ('never', 'former', 'current', 'unknown')",
            name=op.f("ck_patient_profiles_smoking_values"),
        ),
        sa.CheckConstraint(
            "age_years BETWEEN 0 AND 120", name=op.f("ck_patient_profiles_age_bounds")
        ),
        sa.CheckConstraint(
            "height_cm > 0 AND height_cm <= 300", name=op.f("ck_patient_profiles_height_bounds")
        ),
        sa.CheckConstraint(
            "weight_kg > 0 AND weight_kg <= 700", name=op.f("ck_patient_profiles_weight_bounds")
        ),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_patient_profiles_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_profiles")),
        sa.UniqueConstraint("clinical_case_id", name=op.f("uq_patient_profiles_clinical_case_id")),
    )


def downgrade() -> None:
    op.drop_table("patient_profiles")
    op.drop_index(op.f("ix_observations_clinical_case_id"), table_name="observations")
    op.drop_table("observations")
    op.drop_index(op.f("ix_medications_clinical_case_id"), table_name="medications")
    op.drop_table("medications")
    op.drop_index(op.f("ix_conditions_clinical_case_id"), table_name="conditions")
    op.drop_table("conditions")
    op.drop_index(op.f("ix_clinical_notes_clinical_case_id"), table_name="clinical_notes")
    op.drop_table("clinical_notes")
    op.drop_index(op.f("ix_allergies_clinical_case_id"), table_name="allergies")
    op.drop_table("allergies")
