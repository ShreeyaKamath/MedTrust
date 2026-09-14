"""Values are stored as strings with named CHECK constraints, not native enums."""

from enum import StrEnum

from sqlalchemy import Enum


class CaseSourceType(StrEnum):
    SYNTHETIC = "synthetic"
    DEIDENTIFIED = "deidentified"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"
    ESCALATED = "escalated"


def enum_column(enum, name):
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [m.value for m in members],
    )
