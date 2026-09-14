"""Internal persistence contracts; no public CRUD endpoints."""

from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.app.models.enums import AuditOutcome


class AuditEventBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    clinical_case_id: UUID | None = None
    agent_run_id: UUID | None = None
    event_type: str = Field(min_length=1, max_length=128)
    actor_type: str = Field(min_length=1, max_length=64)
    actor_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=128)
    resource_type: str | None = Field(default=None, max_length=128)
    resource_id: str | None = Field(default=None, max_length=128)
    outcome: AuditOutcome
    details: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Safe structured metadata only; no secrets, sensitive records, "
            "full prompts or hidden reasoning."
        ),
    )


class AuditEventCreate(AuditEventBase):
    pass


class AuditEventRead(AuditEventBase):
    id: UUID
    created_at: AwareDatetime
