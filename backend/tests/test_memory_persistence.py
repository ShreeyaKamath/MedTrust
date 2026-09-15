"""Research memory storage, provenance, scope boundaries, and reversible schema."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from alembic import command
from backend.app.db.base import Base
from backend.app.models import AuditEvent
from backend.app.models.memory import MemoryEntry, MemoryEpisode, MemoryRelationship
from backend.app.services.clinical_memory import MemoryRejected
from memory.contracts import RelationType, SelectionRequest, SourceReference


def test_explicit_membership_and_idempotency(memory_env):
    e = memory_env
    assert e.service.create_scope("SYN-MEM-A").id == e.scope.id
    assert e.service.add_episode(e.scope.id, e.cases[0].id).scope_id == e.scope.id
    with pytest.raises(MemoryRejected, match="episode_already_scoped"):
        e.service.add_episode(e.other_scope.id, e.cases[0].id)
    with pytest.raises(MemoryRejected, match="ineligible_case"):
        e.service.add_episode(e.scope.id, uuid4())


def test_verified_source_and_duplicate(memory_env):
    e = memory_env
    row = e.observation()
    a, b = e.ingest(row), e.ingest(row)
    assert a.id == b.id
    assert a.snapshot["value"] == 100
    assert a.snapshot["source_type"] == "synthetic"
    assert a.snapshot["reference"]["record_id"] == str(row.id)
    assert a.available_at == a.created_at == e.clock.now
    assert e.session.scalar(select(func.count()).select_from(MemoryEntry)) == 1
    e.session.commit()
    e.session.expire_all()
    assert e.service.valid_entry(e.session.get(MemoryEntry, a.id))


@pytest.mark.parametrize("change", ["missing", "field", "type", "case", "scope"])
def test_rejected_references_are_audited(memory_env, change):
    e = memory_env
    row = e.observation()
    ref = SourceReference(kind="observation", record_id=row.id, field="value_numeric")
    case_id, scope_id = e.cases[0].id, e.scope.id
    if change == "missing":
        ref.record_id = uuid4()
    if change == "field":
        ref.field = "clinical_case_id"
    if change == "type":
        ref.kind = "medication"
    if change == "case":
        case_id = e.cases[1].id
    if change == "scope":
        scope_id = e.other_scope.id
    with pytest.raises(MemoryRejected):
        e.service.ingest_source(scope_id, case_id, ref)
    assert e.session.scalar(select(func.count()).select_from(MemoryEntry)) == 0
    audit = list(e.session.scalars(select(AuditEvent)))[-1]
    assert audit.event_type == "memory_rejected" and set(audit.details) == {"reason"}


def test_no_cross_scope_selection(memory_env):
    e = memory_env
    a = e.ingest(e.observation())
    b = e.ingest(e.observation(case_index=2), scope_id=e.other_scope.id)
    assert [i.id for i in e.selection().entries] == [a.id]
    with pytest.raises(MemoryRejected):
        e.service.select(
            SelectionRequest(scope_id=e.other_scope.id, case_id=e.cases[0].id, as_of=e.clock.now)
        )
    assert b.scope_id != a.scope_id


def test_source_drift_excluded_and_history_retained(memory_env):
    e = memory_env
    row = e.observation()
    old = e.ingest(row)
    row.value_numeric = 200
    e.session.flush()
    assert not e.selection().entries
    new = e.ingest(row)
    assert new.id != old.id
    assert old.snapshot["value"] == 100
    assert [i.id for i in e.selection().entries] == [new.id]


def test_relationship_guards_history_and_duplicate(memory_env):
    e = memory_env
    a, b = e.ingest(e.observation()), e.ingest(e.observation(110))
    relation = e.service.relate(e.scope.id, b.id, a.id, RelationType.CORRECTS)
    assert e.service.relate(e.scope.id, b.id, a.id, RelationType.CORRECTS).id == relation.id
    assert [i.id for i in e.selection().entries] == [b.id]
    assert e.session.get(MemoryEntry, a.id) is a
    with pytest.raises(MemoryRejected, match="self_relationship"):
        e.service.relate(e.scope.id, a.id, a.id, RelationType.CORRECTS)
    with pytest.raises(MemoryRejected, match="correction_cycle"):
        e.service.relate(e.scope.id, a.id, b.id, RelationType.SUPERSEDES)
    foreign = e.ingest(e.observation(case_index=2), scope_id=e.other_scope.id)
    with pytest.raises(MemoryRejected, match="scope_mismatch"):
        e.service.relate(e.scope.id, a.id, foreign.id, RelationType.CONTRADICTS)


def test_long_correction_cycle_and_symmetric_conflict(memory_env):
    e = memory_env
    a, b, c = [e.ingest(e.observation(i)) for i in (100, 110, 120)]
    e.service.relate(e.scope.id, b.id, a.id, RelationType.CORRECTS)
    e.service.relate(e.scope.id, c.id, b.id, RelationType.SUPERSEDES)
    with pytest.raises(MemoryRejected, match="cycle"):
        e.service.relate(e.scope.id, a.id, c.id, RelationType.CORRECTS)
    first = e.service.relate(e.scope.id, a.id, c.id, RelationType.CONTRADICTS)
    assert e.service.relate(e.scope.id, c.id, a.id, RelationType.CONTRADICTS).id == first.id


def test_rollback_and_restrict(memory_env):
    e = memory_env
    e.ingest(e.observation())
    e.session.rollback()
    assert e.session.scalar(select(func.count()).select_from(MemoryEntry)) == 0
    a = e.ingest(e.observation())
    e.session.commit()
    episode = e.session.scalar(
        select(MemoryEpisode).where(MemoryEpisode.clinical_case_id == a.clinical_case_id)
    )
    e.session.delete(episode)
    with pytest.raises(IntegrityError):
        e.session.flush()
    e.session.rollback()


def test_database_relationship_self_constraint(memory_env):
    e = memory_env
    a = e.ingest(e.observation())
    e.session.add(
        MemoryRelationship(
            scope_id=e.scope.id,
            from_entry_id=a.id,
            to_entry_id=a.id,
            relation_type="corrects",
            available_at=e.clock.now,
        )
    )
    with pytest.raises(IntegrityError):
        e.session.flush()
    e.session.rollback()


def test_database_entry_identity_constraint(memory_env):
    e = memory_env
    first = e.ingest(e.observation())
    e.session.commit()
    values = {
        column.name: getattr(first, column.name)
        for column in MemoryEntry.__table__.columns
        if column.name != "id"
    }
    e.session.add(MemoryEntry(**values))
    with pytest.raises(IntegrityError):
        e.session.flush()
    e.session.rollback()


def test_invalid_scope_label_and_profile_identifier_not_memory(memory_env):
    e = memory_env
    with pytest.raises(MemoryRejected, match="invalid_scope_identifier"):
        e.service.create_scope("patient-demographic-match")
    from memory.provenance import SOURCE_FIELDS

    assert not SOURCE_FIELDS["patient_profile"]


def test_synthetic_scenario_and_cli_validation(memory_env, capsys):
    from scripts.run_memory_scenario import load_fixture, main, run_scenario

    assert len(load_fixture().scenarios) == 10
    assert main(["--validate-only"]) == 0
    assert "validated 10" in capsys.readouterr().out
    report = run_scenario(memory_env.session)
    assert report["passed"] == 10 and all(report["scenarios"].values())


def test_0002_0003_migration_round_trip():
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://")
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002")
        original = set(inspect(connection).get_table_names())
        command.upgrade(config, "0003")
        command.check(config)
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        assert inspect(connection).get_indexes("memory_entries")
        assert inspect(connection).get_check_constraints("memory_entries")
        command.downgrade(config, "0002")
        assert set(inspect(connection).get_table_names()) == original
        command.upgrade(config, "0003")
        command.check(config)
    engine.dispose()
