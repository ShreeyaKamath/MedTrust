"""Deterministic fixture projection. No LLM and no clinical inference."""

import json
from datetime import UTC, datetime

from backend.app.orchestration.contracts import (
    AgentOutput,
    AgentTask,
    EvidenceContext,
    EvidenceRef,
    Fact,
    Finding,
    HistoryContext,
    LabContext,
    MedicationContext,
    ReviewContext,
    Role,
    RuntimeMetadata,
)

MOCK_TIME = datetime(2000, 1, 1, tzinfo=UTC)


class MockAgentRuntime:
    name = "mock"

    def run(self, task: AgentTask) -> AgentOutput:
        facts, missing, questions, refs, contradictions, consistency = [], [], [], [], [], []
        context = task.context
        data = context.model_dump(mode="json")
        if isinstance(context, (HistoryContext, LabContext, MedicationContext)):
            for field, items in data.items():
                if isinstance(items, str):
                    facts.append(Fact(source_field=field, value=items))
                    continue
                if not items:
                    missing.append(field + ": not supplied; absence is not a negative finding")
                for i, item in enumerate(items):
                    source = f"{field}[{i}]"
                    facts.append(
                        Fact(
                            source_field=source,
                            value=json.dumps(item, sort_keys=True),
                            unit=item.get("unit"),
                            reference_range_low=item.get("reference_range_low"),
                            reference_range_high=item.get("reference_range_high"),
                        )
                    )
                    for key, value in item.items():
                        if value is None and len(missing) < 100:
                            missing.append(f"{source}.{key}")
            if isinstance(context, HistoryContext):
                questions = ["reported history versus observed measurement source attribution"]
            elif isinstance(context, LabContext):
                questions = ["laboratory units reference intervals missing values"]
            else:
                questions = ["medication reconciliation missing metadata allergy unknown status"]
        elif isinstance(context, EvidenceContext):
            refs = [EvidenceRef.from_result(r) for b in context.batches for r in b.results]
            missing = ["Evidence is supplied research text; applicability is unassessed."]
            facts = [Fact(source_field=f"evidence:{ref.chunk_id}", value=ref.title) for ref in refs]
        elif isinstance(context, ReviewContext):
            refs = list(
                {ref.chunk_id: ref for o in context.outputs for ref in o.evidence_refs}.values()
            )
            if task.role == Role.CRITIC:
                consistency = [
                    Finding(
                        description="Mock consistency inventory only; no semantic clinical review.",
                        unsupported_statement=True,
                    )
                ]
                missing = ["Human review of supplied findings and evidence is required."]
            else:
                missing = ["Research organization only; no clinical synthesis or recommendations."]
        return AgentOutput(
            run_id=task.run_id,
            agent_name=task.agent_name,
            role=task.role,
            case_id=task.case_id,
            status="completed",
            summary=f"Mock {task.role}: structured supplied-data inventory.",
            facts=facts,
            missing_information=missing,
            evidence_questions=questions,
            evidence_refs=refs,
            contradictions=contradictions,
            consistency_findings=consistency,
            warnings=["MOCK RUN: deterministic software fixture, not LLM output."],
            insufficient_evidence=True,
            started_at=MOCK_TIME,
            completed_at=MOCK_TIME,
            runtime_metadata=RuntimeMetadata(runtime="mock"),
        )
