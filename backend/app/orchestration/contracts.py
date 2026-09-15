"""Phase 6 observable contracts. No medical decision or private reasoning fields."""

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.clinical_details import (
    AllergyCreate,
    ClinicalNoteCreate,
    ConditionCreate,
    MedicationCreate,
    ObservationCreate,
)
from memory.contracts import MemorySelection
from rag.retrieval.schemas import RetrievalResult

Text = Annotated[str, Field(min_length=1, max_length=2000)]
AgentId = Annotated[str, Field(pattern=r"^medtrust-[a-z][a-z0-9-]{0,63}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, revalidate_instances="always")


class Role(StrEnum):
    HISTORY = "history_agent"
    LAB = "lab_agent"
    MEDICATION = "medication_agent"
    EVIDENCE = "evidence_agent"
    CRITIC = "critic_agent"
    COORDINATOR = "coordinator_agent"


class ErrorCategory(StrEnum):
    NOT_INSTALLED = "OpenClawNotInstalled"
    UNAVAILABLE = "OpenClawUnavailable"
    NOT_CONFIGURED = "AgentNotConfigured"
    TIMEOUT = "AgentExecutionTimeout"
    EXECUTION = "AgentExecutionFailed"
    INVALID_OUTPUT = "InvalidAgentOutput"
    RETRIEVAL = "RetrievalUnavailable"
    ORCHESTRATION = "OrchestrationFailed"


class Fact(Contract):
    source_field: Text
    value: str = Field(max_length=20000)
    unit: str | None = Field(default=None, max_length=64)
    reference_range_low: float | None = None
    reference_range_high: float | None = None


class Finding(Contract):
    description: Text
    source_fields: list[Text] = Field(default_factory=list, max_length=100)
    unsupported_statement: bool = Field(default=False, strict=True)


class EvidenceRef(Contract):
    document_id: Text
    chunk_id: Text
    title: Text
    source_reference: Text
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_type: Literal["synthetic", "repository_authored", "permitted_snippet"]
    publisher_or_origin: Text

    @classmethod
    def from_result(cls, result: RetrievalResult) -> Self:
        return cls.model_validate(result.model_dump(include=set(cls.model_fields)))


class AgentFindings(Contract):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    agent_name: AgentId
    role: Role
    case_id: UUID | None = None
    status: Literal["completed", "failed"]
    summary: Text
    facts: list[Fact] = Field(default_factory=list, max_length=300)
    missing_information: list[Text] = Field(default_factory=list, max_length=100)
    contradictions: list[Finding] = Field(default_factory=list, max_length=100)
    consistency_findings: list[Finding] = Field(default_factory=list, max_length=100)
    evidence_questions: list[Text] = Field(default_factory=list, max_length=3)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    insufficient_evidence: bool = Field(default=True, strict=True)
    warnings: list[Text] = Field(default_factory=list, max_length=50)
    requires_human_review: Literal[True] = True
    error: ErrorCategory | None = None

    @model_validator(mode="after")
    def consistent_status(self):
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("Status and error disagree")
        return self


class RuntimeMetadata(Contract):
    runtime: Literal["mock", "openclaw"]
    prompt_id: Literal["medtrust.role"] = "medtrust.role"
    prompt_version: Literal["1.0"] = "1.0"
    model: str | None = Field(default=None, max_length=255)
    provider: str | None = Field(default=None, max_length=128)


class AgentOutput(AgentFindings):
    started_at: AwareDatetime
    completed_at: AwareDatetime
    runtime_metadata: RuntimeMetadata

    @model_validator(mode="after")
    def ordered_times(self):
        if self.completed_at < self.started_at:
            raise ValueError("Timestamps out of order")
        return self


class HistoryContext(Contract):
    summary: str = Field(max_length=20000)
    conditions: list[ConditionCreate] = Field(max_length=100)
    clinical_notes: list[ClinicalNoteCreate] = Field(max_length=100)


class LabContext(Contract):
    observations: list[ObservationCreate] = Field(max_length=100)


class MedicationContext(Contract):
    medications: list[MedicationCreate] = Field(max_length=100)
    allergies: list[AllergyCreate] = Field(max_length=100)


class EvidenceBatch(Contract):
    question: Text
    results: list[RetrievalResult] = Field(max_length=5)


class EvidenceContext(Contract):
    batches: list[EvidenceBatch] = Field(max_length=9)


class ReviewContext(Contract):
    outputs: list[AgentFindings] = Field(max_length=5)


CONTEXT_TYPES = {
    Role.HISTORY: HistoryContext,
    Role.LAB: LabContext,
    Role.MEDICATION: MedicationContext,
    Role.EVIDENCE: EvidenceContext,
    Role.CRITIC: ReviewContext,
    Role.COORDINATOR: ReviewContext,
}


class AgentTask(Contract):
    run_id: UUID
    agent_name: AgentId
    role: Role
    case_id: UUID | None = None
    historical_memory: MemorySelection | None = Field(default=None, exclude_if=lambda v: v is None)
    context: HistoryContext | LabContext | MedicationContext | EvidenceContext | ReviewContext

    @model_validator(mode="after")
    def scoped_context(self):
        if not isinstance(self.context, CONTEXT_TYPES[self.role]):
            raise ValueError("Role context mismatch")
        return self


class State(StrEnum):
    PENDING = "pending"
    VALIDATING_INPUT = "validating_input"
    HISTORY_ANALYSIS = "history_analysis"
    LAB_ANALYSIS = "lab_analysis"
    MEDICATION_ANALYSIS = "medication_analysis"
    EVIDENCE_RETRIEVAL = "evidence_retrieval"
    EVIDENCE_ANALYSIS = "evidence_analysis"
    CRITIC_REVIEW = "critic_review"
    COORDINATOR_SYNTHESIS = "coordinator_synthesis"
    COMPLETED = "completed"
    FAILED = "failed"


class Transition(Contract):
    previous: State
    current: State
    at: AwareDatetime


class Invocation(Contract):
    run_id: UUID
    agent_name: AgentId
    role: Role
    runtime: Literal["mock", "openclaw"]
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    status: Literal["running", "completed", "failed", "invalid"] = "running"
    input_hash: str
    input_bytes: int
    fact_count: int = 0
    evidence_count: int = 0
    error: ErrorCategory | None = None


class RetrievalInvocation(Contract):
    question_hash: str
    mode: Literal["sparse", "dense", "hybrid"]
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    result_count: int = 0
    status: Literal["running", "completed", "failed"] = "running"
    error: ErrorCategory | None = None


class AuditRecord(Contract):
    event: Literal[
        "orchestration_started",
        "agent_invocation_started",
        "agent_invocation_completed",
        "agent_invocation_failed",
        "retrieval_performed",
        "orchestration_completed",
        "orchestration_failed",
    ]
    at: AwareDatetime
    run_id: UUID | None = None


class OrchestrationTrace(Contract):
    orchestration_id: UUID
    case_id: UUID | None
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    transitions: list[Transition] = Field(default_factory=list)
    agent_invocations: list[Invocation] = Field(default_factory=list)
    retrieval_invocations: list[RetrievalInvocation] = Field(default_factory=list)
    events: list[AuditRecord] = Field(default_factory=list)
    errors: list[ErrorCategory] = Field(default_factory=list)
    final_status: State = State.PENDING


class OrchestrationResult(Contract):
    schema_version: Literal["1.0"] = "1.0"
    orchestration_id: UUID
    case_id: UUID | None
    status: Literal["completed", "failed"]
    outputs: list[AgentOutput]
    evidence_refs: list[EvidenceRef]
    warnings: list[str]
    requires_human_review: Literal[True] = True
    trace: OrchestrationTrace
