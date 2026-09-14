"""Initial research persistence records.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_cases",
        sa.Column("external_case_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "synthetic",
                "deidentified",
                name="case_source_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("deidentified", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("deidentified = true", name=op.f("ck_clinical_cases_deidentified_only")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinical_cases")),
        sa.UniqueConstraint("external_case_id", name=op.f("uq_clinical_cases_external_case_id")),
    )
    op.create_table(
        "agent_runs",
        sa.Column("clinical_case_id", sa.Uuid(), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("agent_role", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                name="agent_run_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_provider", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("input_reference", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_agent_runs_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    op.create_index(
        op.f("ix_agent_runs_clinical_case_id"), "agent_runs", ["clinical_case_id"], unique=False
    )
    op.create_table(
        "evidence_records",
        sa.Column("clinical_case_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_title", sa.String(length=255), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("publisher_or_origin", sa.String(length=255), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=255), nullable=False),
        sa.Column("provenance_metadata", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_evidence_records_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_records")),
    )
    op.create_index(
        op.f("ix_evidence_records_clinical_case_id"),
        "evidence_records",
        ["clinical_case_id"],
        unique=False,
    )
    op.create_table(
        "audit_events",
        sa.Column("clinical_case_id", sa.Uuid(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum(
                "success",
                "denied",
                "failed",
                "escalated",
                name="audit_outcome",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("details", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_audit_events_agent_run_id_agent_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_audit_events_clinical_case_id_clinical_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_agent_run_id"), "audit_events", ["agent_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_clinical_case_id"), "audit_events", ["clinical_case_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_clinical_case_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_agent_run_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_evidence_records_clinical_case_id"), table_name="evidence_records")
    op.drop_table("evidence_records")
    op.drop_index(op.f("ix_agent_runs_clinical_case_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_table("clinical_cases")
