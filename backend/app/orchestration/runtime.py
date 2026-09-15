"""Runtime abstraction and strict response binding; no subprocess dependency in workflow."""

import re
from typing import Protocol

from pydantic import ValidationError

from backend.app.orchestration.cli import RuntimeFailure
from backend.app.orchestration.contracts import (
    AgentFindings,
    AgentOutput,
    AgentTask,
    ErrorCategory,
    EvidenceContext,
    EvidenceRef,
    ReviewContext,
    Role,
)


class AgentRuntime(Protocol):
    name: str

    def run(self, task: AgentTask) -> AgentOutput: ...


def validate_findings(data, task: AgentTask) -> AgentFindings:
    try:
        findings = AgentFindings.model_validate(data)
        for key in ("run_id", "agent_name", "role", "case_id"):
            if getattr(findings, key) != getattr(task, key):
                raise ValueError("Response identity mismatch")
        allowed = []
        if isinstance(task.context, EvidenceContext):
            allowed = [EvidenceRef.from_result(r) for b in task.context.batches for r in b.results]
        elif isinstance(task.context, ReviewContext):
            allowed = [ref for output in task.context.outputs for ref in output.evidence_refs]
        if task.role == Role.EVIDENCE and not allowed and not findings.insufficient_evidence:
            raise ValueError("Empty evidence must be marked insufficient")
        if any(ref not in allowed for ref in findings.evidence_refs):
            raise ValueError("Unprovided citation")
        fields = [fact.source_field for fact in findings.facts] + [
            field
            for finding in findings.contradictions + findings.consistency_findings
            for field in finding.source_fields
        ]
        for field in fields:
            if field.startswith("memory"):
                match = re.fullmatch(r"memory\[(\d+)\]", field)
                if (
                    match is None
                    or task.historical_memory is None
                    or int(match[1]) >= len(task.historical_memory.entries)
                ):
                    raise ValueError("Unprovided memory reference")
        if (
            task.role not in {Role.HISTORY, Role.LAB, Role.MEDICATION}
            and findings.evidence_questions
        ):
            raise ValueError("Follow-up retrieval is outside Phase 6")
        return findings
    except (ValidationError, ValueError, TypeError):
        raise RuntimeFailure(ErrorCategory.INVALID_OUTPUT) from None


def validate_output(output: AgentOutput, task: AgentTask, runtime: str) -> AgentOutput:
    try:
        output = AgentOutput.model_validate(output)
        validate_findings(
            output.model_dump(exclude={"started_at", "completed_at", "runtime_metadata"}), task
        )
        if output.runtime_metadata.runtime != runtime:
            raise ValueError("Runtime mismatch")
        return output
    except (ValidationError, ValueError, TypeError):
        raise RuntimeFailure(ErrorCategory.INVALID_OUTPUT) from None
