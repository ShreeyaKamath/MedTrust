"""Optional explicit persistence reuses Phase 3 records; caller owns commit/rollback."""

import json

from sqlalchemy.orm import Session

from backend.app.models import AgentRun, AuditEvent
from backend.app.models.enums import AgentRunStatus, AuditOutcome
from backend.app.orchestration.contracts import OrchestrationResult


def persist_run(session: Session, result: OrchestrationResult) -> None:
    """Persist only trace metadata, never agent prose, prompts, or case narratives.

    Call once per result. Duplicate IDs fail the caller's transaction rather than overwrite.
    AgentRun requires a stored case UUID; fixture-only runs retain the in-memory trace.
    """
    if result.case_id is None:
        raise ValueError("A persisted clinical case is required")
    outputs = {output.run_id: output for output in result.outputs}
    for invocation in result.trace.agent_invocations:
        output = outputs.get(invocation.run_id)
        metadata = output.runtime_metadata if output else None
        session.add(
            AgentRun(
                id=invocation.run_id,
                clinical_case_id=result.case_id,
                agent_name=invocation.agent_name,
                agent_role=invocation.role.value,
                status=AgentRunStatus.COMPLETED
                if invocation.status == "completed"
                else AgentRunStatus.FAILED,
                started_at=invocation.started_at,
                completed_at=invocation.completed_at,
                model_provider=metadata.provider if metadata else None,
                model_name=metadata.model if metadata else None,
                input_reference=invocation.input_hash,
                output_summary=json.dumps(
                    {
                        "fact_count": invocation.fact_count,
                        "evidence_count": invocation.evidence_count,
                    }
                ),
                error_message=invocation.error.value if invocation.error else None,
            )
        )
    session.flush()
    for item in result.trace.events:
        session.add(
            AuditEvent(
                clinical_case_id=result.case_id,
                agent_run_id=item.run_id,
                event_type=item.event,
                actor_type="orchestrator",
                actor_id="medtrust-phase6",
                action=item.event,
                resource_type="orchestration",
                resource_id=str(result.orchestration_id),
                outcome=AuditOutcome.FAILED
                if item.event.endswith("failed")
                else AuditOutcome.SUCCESS,
                details={"at": item.at.isoformat()},
            )
        )
    session.add(
        AuditEvent(
            clinical_case_id=result.case_id,
            event_type="orchestration_trace",
            actor_type="orchestrator",
            actor_id="medtrust-phase6",
            action="record_trace",
            resource_type="orchestration",
            resource_id=str(result.orchestration_id),
            outcome=AuditOutcome.SUCCESS if result.status == "completed" else AuditOutcome.FAILED,
            details=result.trace.model_dump(mode="json"),
        )
    )
    session.flush()
