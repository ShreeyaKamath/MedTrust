"""Deterministic synthetic memory demonstration; default SQLite, always rolled back."""

import argparse
import json
from datetime import timedelta
from pathlib import Path

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.base import Base
from backend.app.models import AgentRun
from backend.app.models.memory import MemoryEvidence
from backend.app.orchestration.memory import MemoryIntegration
from backend.app.orchestration.mock import MockAgentRuntime
from backend.app.orchestration.registry import AgentRegistry
from backend.app.orchestration.workflow import Orchestrator
from backend.app.schemas.clinical_case import ClinicalCaseCreateRequest, ClinicalCaseDetailResponse
from backend.app.services.clinical_cases import create_case, get_case
from backend.app.services.clinical_memory import ClinicalMemoryService, MemoryRejected
from memory.contracts import MemoryContract, RelationType, SelectionRequest, SourceReference
from rag.retrieval.service import RetrievalService
from rag.retrieval.sparse import SparseRetriever
from rag.runtime import load_chunks

DATASET = Path(__file__).resolve().parents[1] / "datasets/synthetic/longitudinal_cases.json"
SCENARIOS = {
    "stable_fact",
    "legitimate_temporal_change",
    "explicit_correction",
    "true_contradiction",
    "unknown_event_time",
    "stale_history",
    "derived_evidence_lineage",
    "cross_scope_rejected",
    "duplicate_ingestion",
    "future_availability_excluded",
}


class ScopeFixture(MemoryContract):
    research_id: str = Field(pattern=r"^SYN-MEM-[A-Z0-9-]{1,48}$")
    episodes: list[str] = Field(min_length=1, max_length=20)


class LongitudinalFixture(MemoryContract):
    schema_version: str
    simulation_time: AwareDatetime
    description: str
    scopes: list[ScopeFixture] = Field(min_length=1, max_length=10)
    cases: list[ClinicalCaseCreateRequest] = Field(min_length=1, max_length=20)
    scenarios: list[str] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def explicit_synthetic_membership(self):
        case_ids = [case.external_case_id for case in self.cases]
        members = [identifier for scope in self.scopes for identifier in scope.episodes]
        if (
            self.schema_version != "1.0"
            or set(self.scenarios) != SCENARIOS
            or len(case_ids) != len(set(case_ids))
            or len(members) != len(set(members))
            or set(members) != set(case_ids)
            or any(c.source_type != "synthetic" for c in self.cases)
            or len({s.research_id for s in self.scopes}) != len(self.scopes)
        ):
            raise ValueError("Invalid reviewed synthetic fixture")
        return self


def load_fixture(path: Path = DATASET) -> LongitudinalFixture:
    return LongitudinalFixture.model_validate_json(path.read_text())


def run_scenario(session: Session) -> dict:
    fixture = load_fixture()
    clock = [fixture.simulation_time]
    service = ClinicalMemoryService(session, lambda: clock[0])
    cases = {c.external_case_id: create_case(session, c) for c in fixture.cases}
    # Simulation-only receipt metadata, explicitly separated from event timestamps.
    for case in cases.values():
        case.created_at = clock[0]
        for row in case.observations:
            row.created_at = clock[0]
    session.flush()
    scopes = {}
    for definition in fixture.scopes:
        scope = service.create_scope(definition.research_id)
        scopes[definition.research_id] = scope
        for identifier in definition.episodes:
            service.add_episode(scope.id, cases[identifier].id)
    scope = scopes["SYN-MEM-DEMO-A"]
    case = cases["MEMCASE-001"]

    def ingest(row, target=scope):
        return service.ingest_source(
            target.id,
            row.clinical_case_id,
            SourceReference(kind="observation", record_id=row.id, field="value_numeric"),
        )

    def select_at(cutoff):
        return service.select(SelectionRequest(scope_id=scope.id, case_id=case.id, as_of=cutoff))

    # ORM refreshes may reorder relationships by UUID; retain the explicit fixture mapping.
    source_rows = list(case.observations)
    entries = [ingest(row) for row in source_rows]
    stable = ingest(cases["MEMCASE-002"].observations[0])
    selected = {item.id: item for item in select_at(clock[0]).entries}
    outcomes = {
        "stable_fact": not selected[stable.id].conflicts and not selected[entries[0].id].conflicts,
        "legitimate_temporal_change": entries[0].id not in selected[entries[1].id].conflicts,
        "true_contradiction": entries[2].id in selected[entries[1].id].conflicts,
        "unknown_event_time": entries[3].event["precision"] == "unknown",
        "stale_history": selected[entries[4].id].components.freshness == 0,
        "duplicate_ingestion": ingest(source_rows[0]).id == entries[0].id,
    }
    service.relate(scope.id, entries[2].id, entries[1].id, RelationType.CORRECTS)
    outcomes["explicit_correction"] = entries[1].id not in {
        i.id for i in select_at(clock[0]).entries
    }
    try:
        ingest(cases["MEMCASE-004"].observations[0])
    except MemoryRejected:
        outcomes["cross_scope_rejected"] = True
    else:
        outcomes["cross_scope_rejected"] = False
    before = clock[0]
    clock[0] += timedelta(days=1)
    future = ingest(cases["MEMCASE-003"].observations[0])
    outcomes["future_availability_excluded"] = future.id not in {
        i.id for i in select_at(before).entries
    }
    _, chunks = load_chunks(Settings(_env_file=None))
    adapter = MemoryIntegration(
        service,
        SelectionRequest(scope_id=scope.id, case_id=cases["MEMCASE-002"].id, as_of=clock[0]),
    )
    runtime = Orchestrator(
        MockAgentRuntime(),
        AgentRegistry.load(),
        RetrievalService(SparseRetriever(chunks)),
        memory=adapter,
    )
    result = runtime.run(
        ClinicalCaseDetailResponse.model_validate(get_case(session, cases["MEMCASE-002"].id))
    )
    created = adapter.persist(result)
    outcomes["derived_evidence_lineage"] = bool(
        created and session.scalar(select(MemoryEvidence)) and session.scalar(select(AgentRun))
    )
    if set(outcomes) != SCENARIOS or not all(outcomes.values()):
        raise ValueError("Synthetic scenario failed")
    return {
        "runtime": "mock",
        "clock": "explicit synthetic simulation",
        "scenarios": dict(sorted(outcomes.items())),
        "passed": len(outcomes),
        "clinical_validation": False,
        "persistent_changes": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        load_fixture()
        if args.validate_only:
            print("validated 10 synthetic memory scenarios")
            return 0
        engine = create_engine("sqlite://", connect_args={"autocommit": False})

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.autocommit = True
            connection.execute("PRAGMA foreign_keys=ON")
            connection.autocommit = False

        try:
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                result = run_scenario(session)
                session.rollback()
                print(json.dumps(result, sort_keys=True, indent=2))
        finally:
            engine.dispose()
        return 0
    except Exception:
        print("Synthetic memory validation failed; inspect offline tests and reviewed fixtures.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
