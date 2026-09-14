"""Synthetic metadata fixtures only; all default tests use in-memory SQLite."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from alembic import command
from backend.app.db.base import Base
from backend.app.models import AgentRun, AuditEvent, ClinicalCase, EvidenceRecord
from backend.app.models.enums import AgentRunStatus
from backend.app.schemas.agent_run import AgentRunCreate, AgentRunRead
from backend.app.schemas.audit import AuditEventCreate, AuditEventRead
from backend.app.schemas.clinical_case import ClinicalCaseCreate, ClinicalCaseRead
from backend.app.schemas.evidence import EvidenceRecordRead

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


def case(**kwargs):
    return ClinicalCase(
        **(
            dict(
                external_case_id="synthetic-001",
                title="Synthetic fixture",
                summary="Research metadata fixture only.",
                source_type="synthetic",
            )
            | kwargs
        )
    )


def evidence(**kwargs):
    return EvidenceRecord(
        **(
            dict(
                source_type="fixture",
                source_title="Synthetic source",
                source_reference="urn:medtrust:synthetic:source-001",
                content_hash="sha256:" + "0" * 64,
            )
            | kwargs
        )
    )


def audit(**kwargs):
    return AuditEvent(
        **(
            dict(
                event_type="fixture_created",
                actor_type="test",
                actor_id="test-harness",
                action="create",
                outcome="success",
            )
            | kwargs
        )
    )


def test_round_trip_relationships_defaults_and_serialization(session):
    before = datetime.now(UTC)
    record = case()
    run = AgentRun(clinical_case=record, agent_name="fixture", agent_role="test")
    source = evidence(clinical_case=record)
    entry = audit(clinical_case=record, agent_run=run, details={"fixture_version": 1})
    session.add_all([record, run, source, entry])
    session.commit()
    session.expire_all()
    assert record.agent_runs == [run]
    assert record.evidence_records == [source]
    assert record.audit_events == run.audit_events == [entry]
    assert run.clinical_case is source.clinical_case is entry.clinical_case is record
    assert entry.agent_run is run
    assert run.status == AgentRunStatus.PENDING
    assert run.started_at is run.completed_at is run.model_name is None
    assert source.provenance_metadata == {}
    assert record.deidentified is True
    objects = [record, run, source, entry]
    assert len({obj.id for obj in objects}) == 4
    for obj, schema in zip(
        objects, [ClinicalCaseRead, AgentRunRead, EvidenceRecordRead, AuditEventRead], strict=True
    ):
        assert isinstance(obj.id, UUID) and obj.id.version == 4
        assert before <= obj.created_at <= datetime.now(UTC)
        payload = schema.model_validate(obj).model_dump(mode="json")
        assert payload["id"] == str(obj.id)
        assert payload["created_at"].endswith("Z")
    original = record.updated_at
    record.title = "Revised synthetic fixture"
    session.commit()
    session.refresh(record)
    assert record.updated_at > original


def test_optional_case_and_run_references(session):
    source, entry = evidence(), audit()
    session.add_all([source, entry])
    session.commit()
    assert source.clinical_case_id is entry.clinical_case_id is entry.agent_run_id is None


@pytest.mark.parametrize("model", [ClinicalCase, AgentRun, EvidenceRecord, AuditEvent])
def test_required_columns(session, model):
    session.add(model())
    with pytest.raises(IntegrityError):
        session.flush()


def test_unique_case_identifier(session):
    session.add_all([case(), case()])
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize("child", ["run", "evidence", "audit"])
def test_parent_delete_preserves_references(session, child):
    record = case()
    linked = {
        "run": lambda: AgentRun(clinical_case=record, agent_name="test", agent_role="test"),
        "evidence": lambda: evidence(clinical_case=record),
        "audit": lambda: audit(clinical_case=record),
    }[child]()
    session.add_all([record, linked])
    session.commit()
    # Also load collections: ORM must not null even nullable child references.
    assert getattr(
        record,
        {"run": "agent_runs", "evidence": "evidence_records", "audit": "audit_events"}[child],
    )
    session.delete(record)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    assert linked.clinical_case_id == record.id


def test_run_delete_and_missing_fk_are_rejected(session):
    run = AgentRun(clinical_case=case(), agent_name="test", agent_role="test")
    entry = audit(agent_run=run)
    session.add(entry)
    session.commit()
    assert run.audit_events == [entry]
    session.delete(run)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.add(evidence(clinical_case_id=uuid4()))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    "factory", [lambda: case(source_type="real_patient"), lambda: audit(outcome="unknown")]
)
def test_invalid_enum_strings(session, factory):
    session.add(factory())
    with pytest.raises(StatementError):
        session.flush()


def test_database_check_constraints(session):
    record = case()
    run = AgentRun(clinical_case=record, agent_name="test", agent_role="test")
    session.add(run)
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE agent_runs SET status = 'invalid'"))
    session.rollback()
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE clinical_cases SET deidentified = false"))


def test_naive_timestamp_rejected(session):
    session.add(evidence(retrieved_at=datetime(2026, 1, 1)))
    with pytest.raises(StatementError, match="Timezone-aware"):
        session.flush()


def test_schema_input_guardrails():
    valid = dict(
        external_case_id="synthetic-001",
        title="Fixture",
        summary="Synthetic only",
        source_type="synthetic",
    )
    for extra in [{"deidentified": False}, {"patient_name": "synthetic-marker"}]:
        with pytest.raises(ValidationError):
            ClinicalCaseCreate(**(valid | extra))
    with pytest.raises(ValidationError):
        AgentRunCreate(
            clinical_case_id=uuid4(), agent_name="test", agent_role="test", status="invalid"
        )
    with pytest.raises(ValidationError):
        AgentRunCreate(
            clinical_case_id=uuid4(),
            agent_name="test",
            agent_role="test",
            started_at=datetime(2026, 1, 1),
        )


def test_schema_has_no_direct_pii_fields():
    forbidden = {
        "full_name",
        "patient_name",
        "email",
        "phone",
        "address",
        "national_id",
        "aadhaar",
        "ssn",
    }
    for table in Base.metadata.tables.values():
        assert forbidden.isdisjoint(table.columns.keys())
    for schema in [
        ClinicalCaseCreate,
        ClinicalCaseRead,
        AgentRunCreate,
        AgentRunRead,
        EvidenceRecordRead,
        AuditEventCreate,
        AuditEventRead,
    ]:
        assert forbidden.isdisjoint(schema.model_fields)


def test_import_and_health_never_connect():
    code = """
from unittest.mock import patch
with patch("sqlalchemy.create_engine", side_effect=AssertionError("engine at import")), \\
     patch("psycopg.connect", side_effect=AssertionError("database connection")):
    import backend.app.db.session
    import backend.app.models
    from backend.app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_migration_round_trip_and_metadata_match():
    config = Config(str(ROOT / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0002"]
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        command.check(config)
        # Exercise persistence through migrated tables, including server timestamp defaults.
        connection.execute(
            text(
                "INSERT INTO clinical_cases "
                "(id, external_case_id, title, summary, source_type, deidentified) "
                "VALUES (:id, 'synthetic-migration', 'Fixture', 'Synthetic only', "
                "'synthetic', true)"
            ),
            {"id": uuid4().hex},
        )
        assert connection.scalar(text("SELECT created_at FROM clinical_cases")) is not None
        # SQLite does not compare CHECK constraints in autogenerate; inspect explicitly.
        for table in Base.metadata.tables.values():
            expected = {
                c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"
            }
            actual = {c["name"] for c in inspect(connection).get_check_constraints(table.name)}
            assert actual == expected
        command.downgrade(config, "0001")
        assert set(inspect(connection).get_table_names()) == {
            "alembic_version",
            "clinical_cases",
            "agent_runs",
            "evidence_records",
            "audit_events",
        }
        assert connection.scalar(text("SELECT count(*) FROM clinical_cases")) == 1
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
    engine.dispose()
