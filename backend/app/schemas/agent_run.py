"""Internal persistence contracts; no public CRUD endpoints."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.app.models.enums import AgentRunStatus


class AgentRunBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    clinical_case_id: UUID
    agent_name: str = Field(min_length=1, max_length=128)
    agent_role: str = Field(min_length=1, max_length=128)
    status: AgentRunStatus = AgentRunStatus.PENDING
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    model_provider: str | None = Field(default=None, max_length=128)
    model_name: str | None = Field(default=None, max_length=255)
    input_reference: str | None = None
    output_summary: str | None = None
    error_message: str | None = None


class AgentRunCreate(AgentRunBase):
    pass


class AgentRunRead(AgentRunBase):
    id: UUID
    created_at: AwareDatetime
