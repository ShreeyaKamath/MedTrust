"""Isolated tests: no local dotenv file or external service is needed."""

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in ("ENV", "API_HOST", "API_PORT", "LOG_LEVEL"):
        monkeypatch.delenv(f"MEDTRUST_{name}", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app():
    from backend.app.main import create_app

    return create_app(Settings(_env_file=None, env="test"))


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def memory_env():
    """Explicit simulation clock; no inference, external services, or local records."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session

    from backend.app.db.base import Base
    from backend.app.models import ClinicalCase, Observation
    from backend.app.services.clinical_memory import ClinicalMemoryService
    from memory.contracts import SelectionRequest, SourceReference

    engine = create_engine("sqlite://", connect_args={"autocommit": False})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.autocommit = True
        connection.execute("PRAGMA foreign_keys=ON")
        connection.autocommit = False

    Base.metadata.create_all(engine)
    clock = SimpleNamespace(now=datetime(2030, 1, 1, tzinfo=UTC))
    with Session(engine, expire_on_commit=False) as session:
        service = ClinicalMemoryService(session, lambda: clock.now)
        scope = service.create_scope("SYN-MEM-A")
        other_scope = service.create_scope("SYN-MEM-B")
        cases = []
        for i in range(3):
            case = ClinicalCase(
                external_case_id=f"MEM-{i}",
                title="Synthetic episode",
                summary="Synthetic source summary",
                source_type="synthetic",
                created_at=clock.now,
            )
            session.add(case)
            session.flush()
            service.add_episode(scope.id if i < 2 else other_scope.id, case.id)
            cases.append(case)

        def observation(value=100, when=None, case_index=0, **kwargs):
            row = Observation(
                clinical_case_id=cases[case_index].id,
                category="laboratory",
                name="Glucose",
                value_numeric=value,
                unit="mg/dL",
                observed_at=when,
                created_at=clock.now,
                **kwargs,
            )
            session.add(row)
            session.flush()
            return row

        def ingest(row, field="value_numeric", scope_id=None):
            return service.ingest_source(
                scope_id or scope.id,
                row.clinical_case_id,
                SourceReference(kind="observation", record_id=row.id, field=field),
            )

        def selection(**kwargs):
            return service.select(
                SelectionRequest(scope_id=scope.id, case_id=cases[0].id, as_of=clock.now, **kwargs)
            )

        session.commit()
        yield SimpleNamespace(
            session=session,
            service=service,
            scope=scope,
            other_scope=other_scope,
            cases=cases,
            clock=clock,
            observation=observation,
            ingest=ingest,
            selection=selection,
            engine=engine,
        )
    engine.dispose()
