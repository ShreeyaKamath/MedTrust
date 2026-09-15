"""Explicit synchronous memory operations. Callers own commit and rollback.

All writers lock the scope row on PostgreSQL, serializing identity and graph changes.
SQLite is supported for serial offline tests, not concurrent production semantics.
"""

import re
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import utc_now
from backend.app.models import AgentRun, AuditEvent, ClinicalCase, EvidenceRecord
from backend.app.models.memory import (
    ClinicalMemoryScope,
    MemoryEntry,
    MemoryEpisode,
    MemoryEvidence,
    MemoryRelationship,
)
from memory.conflicts import contradicts
from memory.contracts import (
    EntryType,
    EventTime,
    MemoryItem,
    MemorySelection,
    RelationType,
    SelectionRequest,
    SourceReference,
    SourceSnapshot,
)
from memory.provenance import SOURCE_MODELS, canonical_json, snapshot, structured_digest
from memory.temporal import confidence, event_visible
from rag.ingestion.chunking import corpus_fingerprint
from rag.ingestion.schemas import EvidenceChunk
from rag.retrieval.schemas import RetrievalResult


class MemoryRejected(ValueError):
    """Fixed reason only; never include source content in errors."""


def audited(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except (ValueError, TypeError, KeyError) as exc:
            reason = str(exc) if isinstance(exc, MemoryRejected) else "invalid_memory_input"
            self.audit("memory_rejected", {"reason": reason}, denied=True)
            raise MemoryRejected(reason) from None

    return wrapped


class ClinicalMemoryService:
    def __init__(self, session: Session, clock: Callable[[], datetime] = utc_now):
        self.session = session
        self.clock = clock

    def now(self) -> datetime:
        return EventTime(precision="datetime", datetime_value=self.clock()).datetime_value

    def audit(self, action: str, details: dict, *, denied: bool = False) -> None:
        self.session.add(
            AuditEvent(
                actor_type="memory_service",
                actor_id="medtrust-phase7",
                event_type=action,
                action=action,
                resource_type="clinical_memory",
                outcome="denied" if denied else "success",
                details=details,
                created_at=self.now(),
            )
        )
        self.session.flush()

    def scope(self, scope_id: UUID, *, lock: bool = False) -> ClinicalMemoryScope:
        query = select(ClinicalMemoryScope).where(ClinicalMemoryScope.id == scope_id)
        if lock:
            query = query.with_for_update()
        result = self.session.scalar(query)
        if result is None:
            raise MemoryRejected("scope_not_found")
        return result

    def membership(
        self, scope_id: UUID, case_id: UUID, as_of: datetime | None = None
    ) -> MemoryEpisode:
        episode = self.session.scalar(
            select(MemoryEpisode).where(
                MemoryEpisode.scope_id == scope_id,
                MemoryEpisode.clinical_case_id == case_id,
            )
        )
        if episode is None or (as_of is not None and episode.created_at > as_of):
            raise MemoryRejected("episode_not_in_scope")
        return episode

    @audited
    def create_scope(self, research_id: str) -> ClinicalMemoryScope:
        if not re.fullmatch(r"SYN-MEM-[A-Z0-9-]{1,48}", research_id):
            raise MemoryRejected("invalid_scope_identifier")
        existing = self.session.scalar(
            select(ClinicalMemoryScope).where(ClinicalMemoryScope.research_id == research_id)
        )
        if existing is not None:
            return existing
        record = ClinicalMemoryScope(research_id=research_id, created_at=self.now())
        self.session.add(record)
        self.session.flush()
        self.audit("memory_scope_created", {"scope_id": str(record.id)})
        return record

    @audited
    def add_episode(self, scope_id: UUID, case_id: UUID) -> MemoryEpisode:
        self.scope(scope_id, lock=True)
        case = self.session.get(ClinicalCase, case_id)
        if (
            case is None
            or not case.deidentified
            or case.source_type not in {"synthetic", "deidentified"}
        ):
            raise MemoryRejected("ineligible_case")
        existing = self.session.scalar(
            select(MemoryEpisode).where(MemoryEpisode.clinical_case_id == case_id)
        )
        if existing is not None:
            if existing.scope_id != scope_id:
                raise MemoryRejected("episode_already_scoped")
            return existing
        record = MemoryEpisode(scope_id=scope_id, clinical_case_id=case_id, created_at=self.now())
        self.session.add(record)
        self.session.flush()
        self.audit("memory_episode_added", {"scope_id": str(scope_id), "case_id": str(case_id)})
        return record

    def source_snapshot(
        self, scope_id: UUID, case_id: UUID, reference: SourceReference
    ) -> SourceSnapshot:
        reference = SourceReference.model_validate(reference)
        self.membership(scope_id, case_id)
        case = self.session.get(ClinicalCase, case_id, populate_existing=True)
        record = self.session.get(
            SOURCE_MODELS[reference.kind], reference.record_id, populate_existing=True
        )
        if case is None or record is None:
            raise MemoryRejected("source_not_found")
        owner = record.id if reference.kind == "clinical_case" else record.clinical_case_id
        if owner != case_id:
            raise MemoryRejected("source_case_mismatch")
        if not case.deidentified or case.source_type not in {"synthetic", "deidentified"}:
            raise MemoryRejected("ineligible_case")
        source = snapshot(record, case, reference)
        if len(canonical_json(source.model_dump())) > 100000:
            raise MemoryRejected("source_snapshot_too_large")
        if (
            reference.kind == "clinical_note"
            and case.source_type == "synthetic"
            and not record.synthetic
        ):
            raise MemoryRejected("ineligible_note")
        return source

    def entries(self, scope_id: UUID) -> list[MemoryEntry]:
        rows = list(
            self.session.scalars(
                select(MemoryEntry).where(MemoryEntry.scope_id == scope_id).limit(10001)
            )
        )
        if len(rows) > 10000:
            raise MemoryRejected("scope_capacity_exceeded")
        return rows

    def relationships(self, scope_id: UUID) -> list[MemoryRelationship]:
        rows = list(
            self.session.scalars(
                select(MemoryRelationship)
                .where(MemoryRelationship.scope_id == scope_id)
                .limit(30001)
            )
        )
        if len(rows) > 30000:
            raise MemoryRejected("relationship_capacity_exceeded")
        return rows

    @audited
    def ingest_source(
        self, scope_id: UUID, case_id: UUID, reference: SourceReference
    ) -> MemoryEntry:
        self.scope(scope_id, lock=True)
        source = self.source_snapshot(scope_id, case_id, reference)
        identity = structured_digest(
            {"kind": "source_fact", "scope": scope_id, "snapshot": source.digest}
        )
        existing = self.session.scalar(
            select(MemoryEntry).where(
                MemoryEntry.scope_id == scope_id, MemoryEntry.identity_digest == identity
            )
        )
        if existing is not None:
            if not self.valid_entry(existing):
                raise MemoryRejected("stored_provenance_invalid")
            return existing
        rows = self.entries(scope_id)
        if len(rows) >= 10000:
            raise MemoryRejected("scope_capacity_exceeded")
        now = self.now()
        if source.source_received_at > now:
            raise MemoryRejected("source_not_yet_available")
        entry = MemoryEntry(
            scope_id=scope_id,
            clinical_case_id=case_id,
            entry_type=EntryType.SOURCE_FACT,
            source_record_id=source.reference.record_id,
            source_kind=source.reference.kind,
            source_field=source.reference.field,
            snapshot=source.model_dump(mode="json"),
            snapshot_digest=source.digest,
            identity_digest=identity,
            event=source.event.model_dump(mode="json"),
            available_at=now,
            created_at=now,
        )
        # Validate comparisons before mutation; malformed history cannot leave a partial insert.
        conflicts = [
            r
            for r in rows
            if r.entry_type == EntryType.SOURCE_FACT
            and self.valid_entry(r)
            and contradicts(source, SourceSnapshot.model_validate(r.snapshot))
        ]
        if len(self.relationships(scope_id)) + len(conflicts) > 30000:
            raise MemoryRejected("relationship_capacity_exceeded")
        self.session.add(entry)
        self.session.flush()
        self.audit(
            "memory_created",
            {"entry_id": str(entry.id), "digest": entry.snapshot_digest, "kind": entry.entry_type},
        )
        for other in conflicts:
            self.relate(scope_id, entry.id, other.id, RelationType.CONTRADICTS)
        return entry

    @audited
    def relate(
        self, scope_id: UUID, from_id: UUID, to_id: UUID, kind: RelationType
    ) -> MemoryRelationship:
        kind = RelationType(kind)
        self.scope(scope_id, lock=True)
        if from_id == to_id:
            raise MemoryRejected("self_relationship")
        a, b = self.session.get(MemoryEntry, from_id), self.session.get(MemoryEntry, to_id)
        if a is None or b is None or a.scope_id != scope_id or b.scope_id != scope_id:
            raise MemoryRejected("relationship_scope_mismatch")
        if a.available_at > self.now() or b.available_at > self.now():
            raise MemoryRejected("relationship_not_yet_available")
        if kind == RelationType.SUPPORTS and (
            a.entry_type != EntryType.SOURCE_FACT or b.entry_type != EntryType.DERIVED_ASSERTION
        ):
            raise MemoryRejected("support_requires_source_and_assertion")
        if (
            kind in {RelationType.CORRECTS, RelationType.SUPERSEDES}
            and a.entry_type != b.entry_type
        ):
            raise MemoryRejected("correction_type_mismatch")
        if kind == RelationType.CONTRADICTS and str(from_id) > str(to_id):
            from_id, to_id = to_id, from_id
        relations = self.relationships(scope_id)
        for relation in relations:
            if (relation.from_entry_id, relation.to_entry_id, relation.relation_type) == (
                from_id,
                to_id,
                kind,
            ):
                return relation
        if len(relations) >= 30000:
            raise MemoryRejected("relationship_capacity_exceeded")
        if kind in {RelationType.CORRECTS, RelationType.SUPERSEDES}:
            graph: dict[UUID, set[UUID]] = {}
            for relation in relations:
                if relation.relation_type in {RelationType.CORRECTS, RelationType.SUPERSEDES}:
                    graph.setdefault(relation.from_entry_id, set()).add(relation.to_entry_id)
            pending, seen = [to_id], set()
            while pending:
                current = pending.pop()
                if current == from_id:
                    raise MemoryRejected("correction_cycle")
                if current not in seen:
                    seen.add(current)
                    pending.extend(graph.get(current, set()))
        row = MemoryRelationship(
            scope_id=scope_id,
            from_entry_id=from_id,
            to_entry_id=to_id,
            relation_type=kind,
            available_at=self.now(),
            created_at=self.now(),
        )
        self.session.add(row)
        self.session.flush()
        self.audit(
            "memory_relationship_created",
            {
                "relationship_id": str(row.id),
                "from_id": str(from_id),
                "to_id": str(to_id),
                "kind": kind,
            },
        )
        return row

    @audited
    def evidence_snapshot(
        self,
        result: RetrievalResult,
        chunks: list[EvidenceChunk],
        retrieved_at: datetime | None = None,
    ) -> dict:
        if len(chunks) > 10000:
            raise MemoryRejected("evidence_capacity_exceeded")
        result = RetrievalResult.model_validate(result)
        supplied = EvidenceChunk.model_validate(
            result.model_dump(include=set(EvidenceChunk.model_fields))
        )
        original = next((c for c in chunks if c.chunk_id == result.chunk_id), None)
        if original is None or supplied != original:
            raise MemoryRejected("unprovided_evidence")
        received = EventTime(
            precision="datetime", datetime_value=retrieved_at or self.now()
        ).datetime_value
        if received > self.now():
            raise MemoryRejected("evidence_not_yet_available")
        return {
            "chunk": supplied.model_dump(mode="json"),
            "corpus_fingerprint": corpus_fingerprint(chunks),
            "retrieved_at": received.isoformat(),
        }

    @audited
    def ingest_derived(
        self,
        scope_id: UUID,
        task,
        output,
        source_ids: list[UUID],
        evidence: list[RetrievalResult],
        chunks: list[EvidenceChunk],
        retrieved_at: dict[str, datetime] | None = None,
    ) -> MemoryEntry:
        # This host API accepts a bound task/output, never model-selected storage IDs.
        from backend.app.orchestration.cli import RuntimeFailure
        from backend.app.orchestration.contracts import AgentTask, EvidenceRef
        from backend.app.orchestration.runtime import validate_output

        task = AgentTask.model_validate(task)
        self.scope(scope_id, lock=True)
        self.membership(scope_id, task.case_id)
        try:
            output = validate_output(output, task, output.runtime_metadata.runtime)
        except RuntimeFailure:
            raise MemoryRejected("invalid_agent_output") from None
        if output.status != "completed" or not source_ids and not evidence:
            raise MemoryRejected("unsupported_assertion")
        if len(source_ids) > 300 or len(evidence) > 50:
            raise MemoryRejected("support_capacity_exceeded")
        run = self.session.get(AgentRun, output.run_id)
        if (
            run is None
            or run.clinical_case_id != task.case_id
            or run.agent_name != task.agent_name
            or run.agent_role != task.role
            or run.status != "completed"
            or run.completed_at is None
            or run.completed_at > self.now()
        ):
            raise MemoryRejected("producing_run_mismatch")
        source_ids = sorted(set(source_ids), key=str)
        for entry_id in source_ids:
            source = self.session.get(MemoryEntry, entry_id)
            if (
                source is None
                or source.scope_id != scope_id
                or source.entry_type != EntryType.SOURCE_FACT
                or source.available_at > self.now()
                or not self.valid_entry(source)
            ):
                raise MemoryRejected("support_scope_or_provenance_invalid")
        if any(EvidenceRef.from_result(r) not in output.evidence_refs for r in evidence):
            raise MemoryRejected("evidence_not_cited")
        # Repeated retrieved chunks and repeated agent citations are a single source.
        unique_evidence = {r.chunk_id: r for r in evidence}
        evidence_data = [
            self.evidence_snapshot(unique_evidence[key], chunks, (retrieved_at or {}).get(key))
            for key in sorted(unique_evidence)
        ]
        payload = {
            "canonicalization": "memory-json-v1",
            "summary": output.summary,
            "run_id": str(run.id),
            "case_id": str(task.case_id),
            "role": task.role.value,
            "source_ids": [str(i) for i in source_ids],
            "evidence": evidence_data,
            "runtime": output.runtime_metadata.model_dump(mode="json"),
            "output_digest": structured_digest(output.model_dump(mode="json")),
        }
        # Retrieval receipt time is not part of retry identity; producing run and exact output are.
        identity = structured_digest(
            {
                "scope": scope_id,
                "run": run.id,
                "output": payload["output_digest"],
                "sources": source_ids,
                "evidence": [
                    {"chunk": d["chunk"], "corpus_fingerprint": d["corpus_fingerprint"]}
                    for d in evidence_data
                ],
            }
        )
        existing = self.session.scalar(
            select(MemoryEntry).where(
                MemoryEntry.scope_id == scope_id, MemoryEntry.identity_digest == identity
            )
        )
        if existing is not None:
            if not self.valid_entry(existing):
                raise MemoryRejected("stored_provenance_invalid")
            return existing
        if (
            len(self.entries(scope_id)) >= 10000
            or len(self.relationships(scope_id)) + len(source_ids) > 30000
        ):
            raise MemoryRejected("scope_capacity_exceeded")
        # Savepoint keeps this compound operation atomic if a database constraint fails.
        with self.session.begin_nested():
            entry = MemoryEntry(
                scope_id=scope_id,
                clinical_case_id=task.case_id,
                entry_type=EntryType.DERIVED_ASSERTION,
                producing_run_id=run.id,
                producing_role=task.role.value,
                snapshot=payload,
                snapshot_digest=structured_digest(payload),
                identity_digest=identity,
                event=EventTime().model_dump(),
                available_at=self.now(),
                created_at=self.now(),
            )
            self.session.add(entry)
            self.session.flush()
            for data in evidence_data:
                chunk = data["chunk"]
                previous = self.session.scalar(
                    select(MemoryEvidence)
                    .join(MemoryEntry, MemoryEvidence.entry_id == MemoryEntry.id)
                    .where(
                        MemoryEntry.clinical_case_id == task.case_id,
                        MemoryEvidence.identity_digest == structured_digest(data),
                    )
                )
                source = (
                    self.session.get(EvidenceRecord, previous.evidence_record_id)
                    if previous
                    else None
                )
                if source is None:
                    source = EvidenceRecord(
                        clinical_case_id=task.case_id,
                        source_type=chunk["source_type"],
                        source_title=chunk["title"],
                        source_reference=chunk["source_reference"],
                        publisher_or_origin=chunk["publisher_or_origin"],
                        publication_date=EvidenceChunk.model_validate(chunk).publication_date,
                        retrieved_at=EventTime(
                            precision="datetime", datetime_value=data["retrieved_at"]
                        ).datetime_value,
                        content_hash=chunk["content_hash"],
                        provenance_metadata=data,
                    )
                self.session.add(source)
                self.session.flush()
                self.session.add(
                    MemoryEvidence(
                        entry_id=entry.id,
                        evidence_record_id=source.id,
                        identity_digest=structured_digest(data),
                        snapshot=data,
                        created_at=self.now(),
                    )
                )
            self.session.flush()
            for source_id in source_ids:
                self.relate(scope_id, source_id, entry.id, RelationType.SUPPORTS)
            self.audit(
                "memory_created",
                {
                    "entry_id": str(entry.id),
                    "digest": entry.snapshot_digest,
                    "kind": entry.entry_type,
                },
            )
        return entry

    def valid_entry(self, entry: MemoryEntry) -> bool:
        try:
            self.membership(entry.scope_id, entry.clinical_case_id)
            if entry.entry_type == EntryType.SOURCE_FACT:
                source = SourceSnapshot.model_validate(entry.snapshot)
                if (
                    source.case_id != entry.clinical_case_id
                    or source.reference.record_id != entry.source_record_id
                    or source.reference.kind != entry.source_kind
                    or source.reference.field != entry.source_field
                    or source.event.model_dump(mode="json") != entry.event
                ):
                    return False
                current = self.source_snapshot(
                    entry.scope_id, entry.clinical_case_id, source.reference
                )
                return current == source and entry.snapshot_digest == source.digest
            if (
                entry.entry_type != EntryType.DERIVED_ASSERTION
                or structured_digest(entry.snapshot) != entry.snapshot_digest
            ):
                return False
            run = self.session.get(AgentRun, entry.producing_run_id)
            if (
                run is None
                or run.clinical_case_id != entry.clinical_case_id
                or run.status != "completed"
                or run.agent_role != entry.producing_role
                or run.completed_at is None
                or run.completed_at > entry.available_at
                or entry.snapshot["run_id"] != str(run.id)
                or entry.snapshot["case_id"] != str(entry.clinical_case_id)
                or entry.snapshot["role"] != entry.producing_role
                or EventTime.model_validate(entry.event).precision != "unknown"
            ):
                return False
            supports = [
                self.session.get(MemoryEntry, UUID(i)) for i in entry.snapshot["source_ids"]
            ]
            if any(
                s is None
                or s.scope_id != entry.scope_id
                or s.entry_type != EntryType.SOURCE_FACT
                or s.available_at > entry.available_at
                or not self.valid_entry(s)
                for s in supports
            ):
                return False
            support_links = list(
                self.session.scalars(
                    select(MemoryRelationship).where(
                        MemoryRelationship.to_entry_id == entry.id,
                        MemoryRelationship.relation_type == RelationType.SUPPORTS,
                    )
                )
            )
            if {r.from_entry_id for r in support_links} != {s.id for s in supports}:
                return False
            if any(r.scope_id != entry.scope_id for r in support_links):
                return False
            links = list(
                self.session.scalars(
                    select(MemoryEvidence).where(MemoryEvidence.entry_id == entry.id)
                )
            )
            if len(links) != len(entry.snapshot["evidence"]):
                return False
            for link in links:
                source = self.session.get(EvidenceRecord, link.evidence_record_id)
                chunk = EvidenceChunk.model_validate(link.snapshot["chunk"])
                if (
                    source is None
                    or source.clinical_case_id != entry.clinical_case_id
                    or source.provenance_metadata != link.snapshot
                    or link.snapshot not in entry.snapshot["evidence"]
                    or link.identity_digest != structured_digest(link.snapshot)
                    or source.content_hash != chunk.content_hash
                    or source.source_reference != chunk.source_reference
                    or source.source_type != chunk.source_type
                    or source.source_title != chunk.title
                    or source.publisher_or_origin != chunk.publisher_or_origin
                    or source.publication_date != chunk.publication_date
                    or source.retrieved_at
                    != EventTime(
                        precision="datetime", datetime_value=link.snapshot["retrieved_at"]
                    ).datetime_value
                    or source.retrieved_at > entry.available_at
                ):
                    return False
            return bool(supports or links)
        except (ValueError, TypeError, KeyError):
            return False

    @audited
    def select(self, request: SelectionRequest) -> MemorySelection:
        request = SelectionRequest.model_validate(request)
        self.scope(request.scope_id, lock=True)
        self.membership(request.scope_id, request.case_id, request.as_of)
        rows = self.entries(request.scope_id)
        eligible = {
            r.id: r
            for r in rows
            if r.available_at <= request.as_of
            and r.created_at <= request.as_of
            and self.valid_entry(r)
            and event_visible(EventTime.model_validate(r.event), request.as_of)
        }
        # Episode membership must also have existed at the cutoff for each historical source.
        for entry_id, row in list(eligible.items()):
            try:
                self.membership(request.scope_id, row.clinical_case_id, request.as_of)
            except MemoryRejected:
                del eligible[entry_id]
        relations = [
            r
            for r in self.relationships(request.scope_id)
            if r.available_at <= request.as_of
            and r.from_entry_id in eligible
            and r.to_entry_id in eligible
        ]
        invalidated = {
            r.to_entry_id
            for r in relations
            if r.relation_type in {RelationType.CORRECTS, RelationType.SUPERSEDES}
        }
        active = {key: row for key, row in eligible.items() if key not in invalidated}
        for entry_id, row in list(active.items()):
            if row.entry_type == EntryType.DERIVED_ASSERTION and any(
                UUID(i) not in active for i in row.snapshot["source_ids"]
            ):
                del active[entry_id]
        conflicts: dict[UUID, set[UUID]] = {}
        for relation in relations:
            if (
                relation.relation_type == RelationType.CONTRADICTS
                and relation.from_entry_id in active
                and relation.to_entry_id in active
            ):
                conflicts.setdefault(relation.from_entry_id, set()).add(relation.to_entry_id)
                conflicts.setdefault(relation.to_entry_id, set()).add(relation.from_entry_id)
        selection = MemorySelection(
            scope_id=request.scope_id, as_of=request.as_of, excluded_count=len(rows) - len(active)
        )
        ordered = sorted(
            active.values(), key=lambda r: (r.available_at, r.identity_digest), reverse=True
        )
        for row in ordered:
            event = EventTime.model_validate(row.event)
            links = list(
                self.session.scalars(
                    select(MemoryEvidence.evidence_record_id).where(
                        MemoryEvidence.entry_id == row.id
                    )
                )
            )
            item = MemoryItem(
                id=row.id,
                case_id=row.clinical_case_id,
                entry_type=row.entry_type,
                source_kind=row.source_kind,
                field=row.source_field,
                value=row.snapshot["value"]
                if row.entry_type == EntryType.SOURCE_FACT
                else row.snapshot["summary"],
                event=event,
                available_at=row.available_at,
                digest=row.snapshot_digest,
                producing_role=row.producing_role,
                source_ids=row.snapshot.get("source_ids", []),
                evidence_ids=sorted(links, key=str),
                conflicts=sorted(conflicts.get(row.id, set()), key=str)[:100],
                conflicts_omitted_count=max(0, len(conflicts.get(row.id, set())) - 100),
                components=confidence(
                    EntryType(row.entry_type),
                    event,
                    request.as_of,
                    request.freshness_days,
                    bool(conflicts.get(row.id)),
                ),
            )
            proposed = selection.model_copy(update={"entries": [*selection.entries, item]})
            # Budget covers the complete serialized selection, including omission metadata.
            proposed.omitted_count = len(active)
            proposed.characters = request.max_characters
            if (
                len(selection.entries) >= request.max_entries
                or len(proposed.model_dump_json()) > request.max_characters
            ):
                selection.omitted_count += 1
            else:
                selection.entries.append(item)
        selection.characters = len(selection.model_dump_json())
        selection.characters = len(selection.model_dump_json())
        self.audit(
            "memory_selected",
            {
                "scope_id": str(request.scope_id),
                "case_id": str(request.case_id),
                "as_of": request.as_of.isoformat(),
                "selected": len(selection.entries),
                "omitted": selection.omitted_count,
                "excluded": selection.excluded_count,
                "snapshot_digest": structured_digest(selection.model_dump(mode="json")),
            },
        )
        return selection
