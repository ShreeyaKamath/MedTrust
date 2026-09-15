"""Optional host-owned adapter. Persistence is explicit and only for completed runs."""

from datetime import datetime
from uuid import UUID

from backend.app.orchestration.context import validate_case
from backend.app.orchestration.contracts import (
    AgentOutput,
    AgentTask,
    EvidenceRef,
    OrchestrationResult,
    Role,
)
from backend.app.orchestration.persistence import persist_run
from backend.app.schemas.clinical_case import ClinicalCaseDetailResponse
from backend.app.services.clinical_cases import get_case
from backend.app.services.clinical_memory import ClinicalMemoryService, MemoryRejected, audited
from memory.contracts import (
    EntryType,
    MemorySelection,
    SelectionRequest,
    SourceKind,
    SourceReference,
)
from memory.provenance import SOURCE_FIELDS
from rag.ingestion.schemas import EvidenceChunk
from rag.retrieval.schemas import RetrievalResult

ROLE_KINDS = {
    Role.HISTORY: {SourceKind.CASE, SourceKind.CONDITION, SourceKind.NOTE},
    Role.LAB: {SourceKind.OBSERVATION},
    Role.MEDICATION: {SourceKind.MEDICATION, SourceKind.ALLERGY},
    Role.EVIDENCE: set(),
    Role.CRITIC: set(),
    Role.COORDINATOR: set(),
}
DETAIL_KINDS = {
    "conditions": SourceKind.CONDITION,
    "observations": SourceKind.OBSERVATION,
    "medications": SourceKind.MEDICATION,
    "allergies": SourceKind.ALLERGY,
    "clinical_notes": SourceKind.NOTE,
}


class MemoryIntegration:
    """One host-controlled execution at a time; no hidden process-global state."""

    def __init__(self, service: ClinicalMemoryService, request: SelectionRequest):
        self.service = service
        self.request = SelectionRequest.model_validate(request)
        self.selection: MemorySelection | None = None
        self.orchestration_id: UUID | None = None
        self.captured: list[tuple[AgentTask, AgentOutput]] = []
        self.evidence: dict[str, RetrievalResult] = {}
        self.chunks: list[EvidenceChunk] = []
        self.source_map: dict[str, list[SourceReference]] = {}
        self.source_digests: dict[str, str] = {}
        self.retrieved_at: dict[str, datetime] = {}

    def audit(self, action: str, details: dict, *, denied: bool = False) -> None:
        self.service.audit(action, details, denied=denied)

    @audited
    def prepare(self, case, orchestration_id: UUID) -> None:
        self.captured, self.evidence, self.chunks = [], {}, []
        self.source_map, self.source_digests = {}, {}
        self.retrieved_at = {}
        self.selection = None
        self.orchestration_id = orchestration_id
        if not isinstance(case, ClinicalCaseDetailResponse) or case.id != self.request.case_id:
            raise MemoryRejected("persisted_case_required")
        stored = get_case(self.service.session, case.id)
        if stored is None or validate_case(
            ClinicalCaseDetailResponse.model_validate(stored)
        ) != validate_case(case):
            raise MemoryRejected("case_snapshot_mismatch")
        self.selection = self.service.select(self.request)
        self.source_map["summary"] = [
            SourceReference(kind=SourceKind.CASE, record_id=case.id, field="summary")
        ]
        for group, kind in DETAIL_KINDS.items():
            for index, row in enumerate(getattr(case, group)):
                refs = [
                    SourceReference(kind=kind, record_id=row.id, field=field)
                    for field in sorted(SOURCE_FIELDS[kind])
                    if getattr(row, field) is not None
                ]
                self.source_map[f"{group}[{index}]"] = refs
                for ref in refs:
                    self.source_map[f"{group}[{index}].{ref.field}"] = [ref]
        for refs in self.source_map.values():
            for ref in refs:
                key = ref.model_dump_json()
                self.source_digests[key] = self.service.source_snapshot(
                    self.request.scope_id, case.id, ref
                ).digest

    def project(self, role: Role) -> MemorySelection:
        if self.selection is None:
            raise MemoryRejected("memory_not_prepared")
        entries = [
            item
            for item in self.selection.entries
            if (
                item.entry_type == EntryType.SOURCE_FACT
                and item.source_kind in ROLE_KINDS[role]
                or item.entry_type == EntryType.DERIVED_ASSERTION
                and (item.producing_role == role or role in {Role.CRITIC, Role.COORDINATOR})
            )
        ]
        result = self.selection.model_copy(deep=True, update={"entries": entries})
        result.omitted_count += len(self.selection.entries) - len(entries)
        result.characters = len(result.model_dump_json())
        result.characters = len(result.model_dump_json())
        return result

    def capture(self, task: AgentTask, output: AgentOutput) -> None:
        self.captured.append((task.model_copy(deep=True), output.model_copy(deep=True)))

    def capture_evidence(self, results: list[RetrievalResult], chunks: list[EvidenceChunk]) -> None:
        for result in results:
            self.service.evidence_snapshot(result, chunks)
            self.evidence[result.chunk_id] = result.model_copy(deep=True)
            self.retrieved_at.setdefault(result.chunk_id, self.service.now())
        self.chunks = [chunk.model_copy(deep=True) for chunk in chunks]

    @audited
    def persist(self, result: OrchestrationResult) -> list[UUID]:
        if (
            result.status != "completed"
            or result.orchestration_id != self.orchestration_id
            or result.case_id != self.request.case_id
            or result.outputs != [output for _, output in self.captured]
        ):
            raise MemoryRejected("completed_bound_result_required")
        created = []
        with self.service.session.begin_nested():
            persist_run(self.service.session, result)
            for task, output in self.captured:
                support_ids = set()
                refs: dict[str, SourceReference] = {}
                for fact in output.facts:
                    if fact.source_field.startswith("memory["):
                        index = int(fact.source_field[7:-1])
                        item = task.historical_memory.entries[index]
                        # Copies of derived prose are not independent evidence.
                        if item.entry_type == EntryType.SOURCE_FACT:
                            support_ids.add(item.id)
                        continue
                    if (
                        task.role in {Role.HISTORY, Role.LAB, Role.MEDICATION}
                        and fact.source_field not in self.source_map
                    ):
                        raise MemoryRejected("unprovided_source_field")
                    for ref in self.source_map.get(fact.source_field, []):
                        if ref.kind not in ROLE_KINDS[task.role]:
                            raise MemoryRejected("source_role_mismatch")
                        refs[ref.model_dump_json()] = ref
                if len(refs) + len(support_ids) > 300:
                    raise MemoryRejected("support_capacity_exceeded")
                for key, ref in refs.items():
                    current = self.service.source_snapshot(
                        self.request.scope_id, result.case_id, ref
                    )
                    if current.digest != self.source_digests[key]:
                        raise MemoryRejected("source_changed_during_run")
                    support_ids.add(
                        self.service.ingest_source(self.request.scope_id, result.case_id, ref).id
                    )
                evidence = [
                    self.evidence[ref.chunk_id]
                    for ref in output.evidence_refs
                    if ref.chunk_id in self.evidence
                    and EvidenceRef.from_result(self.evidence[ref.chunk_id]) == ref
                ]
                if support_ids or evidence:
                    entry = self.service.ingest_derived(
                        self.request.scope_id,
                        task,
                        output,
                        sorted(support_ids, key=str),
                        evidence,
                        self.chunks,
                        self.retrieved_at,
                    )
                    created.append(entry.id)
        return created
