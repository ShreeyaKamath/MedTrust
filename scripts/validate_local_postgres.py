"""Opt-in PostgreSQL integration validation in a transaction that is always rolled back.

Uses the local Compose development database only. A temporary schema isolates all
migration and fixture writes from the development records. Run from repository root.
"""

import json
import subprocess
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.session import get_engine
from backend.app.models import ClinicalCase
from backend.app.schemas.clinical_case import ClinicalCaseDetailResponse
from backend.app.services.clinical_cases import get_case
from scripts.run_memory_scenario import run_scenario
from scripts.seed_synthetic_cases import DATASET, load_dataset, seed_cases


def main() -> None:
    settings = get_settings()
    config_result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    service = json.loads(config_result.stdout)["services"]["postgres"]
    environment = service["environment"]
    url = make_url(settings.database_url.get_secret_value())
    if not (
        settings.env == "development"
        and url.drivername == "postgresql+psycopg"
        and url.host in {"127.0.0.1", "localhost"}
        and url.database == environment["POSTGRES_DB"] == "medtrust"
        and url.username == environment["POSTGRES_USER"]
        and url.password == environment["POSTGRES_PASSWORD"]
        and any(
            str(url.port or 5432) == str(port["published"]) and port["host_ip"] == "127.0.0.1"
            for port in service["ports"]
        )
    ):
        raise RuntimeError("Validation requires the explicit local MedTrust development database")
    engine = get_engine()
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                # Identifier contains only a fixed prefix and generated hexadecimal characters.
                schema = "phase7_validation_" + uuid4().hex
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                config = Config(str(DATASET.parents[2] / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                command.check(config)
                tables = set(inspect(connection).get_table_names(schema=schema))
                assert tables == set(Base.metadata.tables) | {"alembic_version"}
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    assert seed_cases(session, load_dataset()) == (10, 0)
                    assert seed_cases(session, load_dataset()) == (0, 10)
                    ids = list(session.scalars(select(ClinicalCase.id)))
                    for case_id in ids:
                        detail = ClinicalCaseDetailResponse.model_validate(
                            get_case(session, case_id)
                        )
                        assert detail.patient_profile and detail.clinical_notes
                    session.commit()
                print("PostgreSQL: base -> 0003; 10 nested cases round-tripped; rerun skipped 10")
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    report = run_scenario(session)
                    assert report["passed"] == 10
                    session.rollback()
                print(
                    "PostgreSQL: 10 Phase 7 synthetic scenarios passed; scenario writes rolled back"
                )
                command.downgrade(config, "0002")
                assert connection.scalar(select(func.count()).select_from(ClinicalCase)) == 10
                assert "memory_entries" not in inspect(connection).get_table_names(schema=schema)
                command.upgrade(config, "0003")
                command.check(config)
                command.downgrade(config, "0001")
                assert connection.scalar(select(func.count()).select_from(ClinicalCase)) == 10
                assert set(inspect(connection).get_table_names(schema=schema)) == {
                    "alembic_version",
                    "clinical_cases",
                    "agent_runs",
                    "evidence_records",
                    "audit_events",
                }
                command.upgrade(config, "head")
                command.downgrade(config, "base")
                assert inspect(connection).get_table_names(schema=schema) == ["alembic_version"]
                command.upgrade(config, "head")
                print("PostgreSQL: 0003 -> 0002 -> 0003 -> 0001 -> 0003 -> base -> 0003 passed")
            finally:
                transaction.rollback()
        print("Temporary schema and test records rolled back; development records preserved")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Do not expose SQL, credentials or input via diagnostic tracebacks.
        raise SystemExit(
            "PostgreSQL validation failed; check local configuration and migrations"
        ) from None
