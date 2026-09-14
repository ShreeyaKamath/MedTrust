"""A fixed DAG: three specialists, bounded RAG, evidence, critic, coordinator. No retries."""

import hashlib
import logging
from uuid import uuid4

from backend.app.db.base import utc_now
from backend.app.orchestration.cli import RuntimeFailure
from backend.app.orchestration.context import build_context, validate_case
from backend.app.orchestration.contracts import (
    AgentFindings,
    AgentTask,
    AuditRecord,
    ErrorCategory,
    EvidenceBatch,
    EvidenceContext,
    Invocation,
    OrchestrationResult,
    OrchestrationTrace,
    RetrievalInvocation,
    ReviewContext,
    Role,
    State,
    Transition,
)
from backend.app.orchestration.registry import AgentRegistry
from backend.app.orchestration.runtime import AgentRuntime, validate_output
from backend.app.schemas.clinical_case import ClinicalCaseCreateRequest, ClinicalCaseDetailResponse
from rag.retrieval.service import RetrievalService

logger = logging.getLogger("medtrust.orchestration")
ORDER = list(State)[:-1]
TRANSITIONS = {state: {ORDER[i + 1], State.FAILED} for i, state in enumerate(ORDER[:-1])}
TRANSITIONS[State.COMPLETED] = set()
TRANSITIONS[State.FAILED] = set()


def transition(trace: OrchestrationTrace, target: State) -> None:
    if target not in TRANSITIONS[trace.final_status]:
        raise ValueError("Invalid orchestration state transition")
    trace.transitions.append(Transition(previous=trace.final_status, current=target, at=utc_now()))
    trace.final_status = target


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def event(trace: OrchestrationTrace, name: str, run_id=None):
    record = AuditRecord(event=name, at=utc_now(), run_id=run_id)
    trace.events.append(record)
    # Fixed message only; structured formatter omits arbitrary extras by design.
    logger.info(record.event)


def review_context(outputs):
    return ReviewContext(
        outputs=[
            AgentFindings.model_validate(
                o.model_dump(exclude={"started_at", "completed_at", "runtime_metadata", "facts"})
            )
            for o in outputs
        ]
    )


class Orchestrator:
    def __init__(
        self,
        runtime: AgentRuntime,
        registry: AgentRegistry,
        retrieval: RetrievalService,
        mode: str = "sparse",
    ):
        if mode not in {"sparse", "dense", "hybrid"}:
            raise ValueError("Unknown retrieval mode")
        if runtime.name not in {"mock", "openclaw"}:
            raise ValueError("Unknown runtime")
        self.runtime, self.registry, self.retrieval, self.mode = runtime, registry, retrieval, mode

    def run(
        self, case: ClinicalCaseCreateRequest | ClinicalCaseDetailResponse
    ) -> OrchestrationResult:
        case_id = case.id if isinstance(case, ClinicalCaseDetailResponse) else None
        trace = OrchestrationTrace(orchestration_id=uuid4(), case_id=case_id, started_at=utc_now())
        outputs = []
        event(trace, "orchestration_started")

        def invoke(role, context):
            task = AgentTask(
                run_id=uuid4(),
                agent_name=self.registry.roles[role].agent_id,
                role=role,
                case_id=case_id,
                context=context,
            )
            serialized = context.model_dump_json()
            invocation = Invocation(
                run_id=task.run_id,
                agent_name=task.agent_name,
                role=role,
                runtime=self.runtime.name,
                started_at=utc_now(),
                input_hash=digest(serialized),
                input_bytes=len(serialized.encode()),
            )
            trace.agent_invocations.append(invocation)
            event(trace, "agent_invocation_started", task.run_id)
            try:
                output = validate_output(self.runtime.run(task), task, self.runtime.name)
                if output.status != "completed":
                    raise RuntimeFailure(output.error or ErrorCategory.EXECUTION)
                invocation.status = "completed"
                invocation.fact_count, invocation.evidence_count = (
                    len(output.facts),
                    len(output.evidence_refs),
                )
                outputs.append(output)
                event(trace, "agent_invocation_completed", task.run_id)
            except Exception as exc:
                category = (
                    exc.category if isinstance(exc, RuntimeFailure) else ErrorCategory.EXECUTION
                )
                invocation.status = (
                    "invalid" if category == ErrorCategory.INVALID_OUTPUT else "failed"
                )
                invocation.error = category
                event(trace, "agent_invocation_failed", task.run_id)
                raise RuntimeFailure(category) from None
            finally:
                invocation.completed_at = utc_now()

        try:
            transition(trace, State.VALIDATING_INPUT)
            validated = validate_case(case)
            for role, state in (
                (Role.HISTORY, State.HISTORY_ANALYSIS),
                (Role.LAB, State.LAB_ANALYSIS),
                (Role.MEDICATION, State.MEDICATION_ANALYSIS),
            ):
                transition(trace, state)
                invoke(role, build_context(validated, role))
            transition(trace, State.EVIDENCE_RETRIEVAL)
            questions = list(dict.fromkeys(q for o in outputs for q in o.evidence_questions))
            batches = []
            # Schema limits each specialist to three questions, maximum nine queries, top five.
            for question in questions:
                retrieval_run = RetrievalInvocation(
                    question_hash=digest(question), mode=self.mode, started_at=utc_now()
                )
                trace.retrieval_invocations.append(retrieval_run)
                try:
                    results = self.retrieval.retrieve_evidence(question, top_k=5, mode=self.mode)
                    batch = EvidenceBatch(question=question, results=results)
                    batches.append(batch)
                    retrieval_run.result_count = len(results)
                    retrieval_run.status = "completed"
                    event(trace, "retrieval_performed")
                except Exception:
                    retrieval_run.status, retrieval_run.error = "failed", ErrorCategory.RETRIEVAL
                    raise RuntimeFailure(ErrorCategory.RETRIEVAL) from None
                finally:
                    retrieval_run.completed_at = utc_now()
            transition(trace, State.EVIDENCE_ANALYSIS)
            invoke(Role.EVIDENCE, EvidenceContext(batches=batches))
            transition(trace, State.CRITIC_REVIEW)
            invoke(Role.CRITIC, review_context(outputs))
            transition(trace, State.COORDINATOR_SYNTHESIS)
            invoke(Role.COORDINATOR, review_context(outputs))
            transition(trace, State.COMPLETED)
            event(trace, "orchestration_completed")
        except Exception as exc:
            trace.errors.append(
                exc.category if isinstance(exc, RuntimeFailure) else ErrorCategory.ORCHESTRATION
            )
            transition(trace, State.FAILED)
            event(trace, "orchestration_failed")
        trace.completed_at = utc_now()
        refs = list({ref.chunk_id: ref for o in outputs for ref in o.evidence_refs}.values())
        return OrchestrationResult(
            orchestration_id=trace.orchestration_id,
            case_id=case_id,
            status="completed" if trace.final_status == State.COMPLETED else "failed",
            outputs=outputs,
            evidence_refs=refs,
            trace=trace,
            warnings=[
                "Research only; human review required. "
                "Retrieval relevance is not clinical validity.",
                "Partial outputs are not a completed summary."
                if trace.errors
                else "No clinical decisions generated by the orchestration workflow.",
            ],
        )
