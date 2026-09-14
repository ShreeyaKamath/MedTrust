"""Deterministic Phase 4 tests using an isolated temporary SQLite database."""

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.models import (
    Allergy,
    ClinicalCase,
    ClinicalNote,
    Condition,
    Medication,
    Observation,
    PatientProfile,
)
from backend.app.schemas.clinical_case import ClinicalCaseCreateRequest, ClinicalCaseDetailResponse
from backend.app.schemas.clinical_details import (
    AllergyCreate,
    ClinicalNoteCreate,
    ConditionCreate,
    MedicationCreate,
    ObservationCreate,
    PatientProfileCreate,
)
from backend.app.services.clinical_cases import create_case, get_case
from scripts.seed_synthetic_cases import load_dataset, seed_cases


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'cases.db'}",
        connect_args={"check_same_thread": False, "autocommit": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.autocommit = True
        connection.execute("PRAGMA foreign_keys=ON")
        connection.autocommit = False

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def case_client(app, engine):
    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def payload():
    data = load_dataset()[0].model_dump(mode="json")
    data["allergies"] = [{"substance": "Synthetic substance", "severity": "unknown"}]
    data["observations"].append(
        {"category": "history", "name": "Context", "value_text": "Unavailable"}
    )
    return data


def test_all_resources_round_trip_and_relationships(session, payload):
    record = create_case(session, ClinicalCaseCreateRequest.model_validate(payload))
    case_id = record.id
    session.commit()
    session.expunge_all()
    stored = get_case(session, case_id)
    assert stored.patient_profile.synthetic_patient_id == "SYN-P001"
    assert stored.patient_profile.clinical_case is stored
    for field, model in [
        ("conditions", Condition),
        ("observations", Observation),
        ("medications", Medication),
        ("allergies", Allergy),
        ("clinical_notes", ClinicalNote),
    ]:
        children = getattr(stored, field)
        assert children and all(isinstance(child, model) for child in children)
        assert all(child.clinical_case is stored for child in children)
    values = {o.name: o for o in stored.observations}
    assert values["Systolic blood pressure"].value_numeric == 138
    assert values["Context"].value_text == "Unavailable"
    assert stored.clinical_notes[0].synthetic is True
    response = ClinicalCaseDetailResponse.model_validate(stored)
    assert response.id == case_id
    assert response.patient_profile.updated_at.tzinfo is not None


def test_note_defaults(session, payload):
    assert ClinicalNoteCreate(note_type="fixture", content="Synthetic narrative").synthetic is True
    record = ClinicalCase(
        **{
            k: payload[k]
            for k in ("external_case_id", "title", "summary", "source_type", "deidentified")
        }
    )
    note = ClinicalNote(clinical_case=record, note_type="fixture", content="Synthetic narrative")
    session.add(note)
    session.commit()
    assert note.synthetic is True


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"value_text": "   "},
        {"value_numeric": 1},
        {"value_numeric": float("nan"), "unit": "1"},
        {"value_numeric": float("inf"), "unit": "1"},
        {"value_numeric": 1, "unit": "1", "reference_range_low": 3, "reference_range_high": 2},
        {"value_text": "Supplied", "observed_at": "2026-01-01T00:00:00"},
    ],
)
def test_observation_invalid(values):
    with pytest.raises(ValidationError):
        ObservationCreate(category="fixture", name="Measurement", **values)


def test_zero_numeric_and_text_values():
    assert (
        ObservationCreate(category="fixture", name="Count", value_numeric=0, unit="1").value_numeric
        == 0
    )
    assert (
        ObservationCreate(category="fixture", name="Context", value_text="Missing").value_text
        == "Missing"
    )


@pytest.mark.parametrize(
    "schema,values",
    [
        (PatientProfileCreate, {"synthetic_patient_id": "MRN-123"}),
        (PatientProfileCreate, {"synthetic_patient_id": "SYN-P001", "age_years": -1}),
        (PatientProfileCreate, {"synthetic_patient_id": "SYN-P001", "recorded_sex": "invalid"}),
        (ConditionCreate, {"name": "Fixture", "status": "invalid"}),
        (MedicationCreate, {"name": "Fixture", "status": "invalid"}),
        (
            MedicationCreate,
            {"name": "Fixture", "start_date": "2026-02-01", "end_date": "2026-01-01"},
        ),
        (AllergyCreate, {"substance": "Fixture", "severity": "invalid"}),
        (ClinicalNoteCreate, {"note_type": "fixture", "content": " "}),
    ],
)
def test_resource_validation(schema, values):
    with pytest.raises(ValidationError):
        schema.model_validate(values)


def test_nested_api_create_get_duplicate_and_missing(case_client, payload):
    response = case_client.post("/api/v1/cases", json=payload)
    assert response.status_code == 201, response.text
    created = response.json()
    UUID(created["id"])
    fetched = case_client.get(f"/api/v1/cases/{created['id']}")
    assert fetched.status_code == 200
    # Collections have stable database ordering; input order is not an API contract.
    for key in ("conditions", "observations", "medications", "allergies", "clinical_notes"):
        created[key] = sorted(created[key], key=lambda item: item["id"])
    result = fetched.json()
    for key in ("conditions", "observations", "medications", "allergies", "clinical_notes"):
        result[key] = sorted(result[key], key=lambda item: item["id"])
    assert result == created
    duplicate = case_client.post("/api/v1/cases", json=payload)
    assert duplicate.status_code == 409
    assert "CASE-001" not in duplicate.text and "INSERT" not in duplicate.text
    assert case_client.get(f"/api/v1/cases/{uuid4()}").status_code == 404
    assert case_client.get("/api/v1/cases/not-a-uuid").status_code == 422


PII_FIELDS = [
    "patient_name",
    "full_name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "address",
    "aadhaar",
    "ssn",
    "national_id",
]


@pytest.mark.parametrize("field", PII_FIELDS)
def test_pii_rejected_at_every_level(payload, field):
    for resource in (
        None,
        "patient_profile",
        "conditions",
        "observations",
        "medications",
        "allergies",
        "clinical_notes",
    ):
        data = deepcopy(payload)
        target = data if resource is None else data[resource]
        if isinstance(target, list):
            target = target[0]
        target[field] = "synthetic-rejection-marker"
        with pytest.raises(ValidationError):
            ClinicalCaseCreateRequest.model_validate(data)
    for table in Base.metadata.tables.values():
        assert field not in table.columns


@pytest.mark.parametrize(
    "change",
    [
        {"deidentified": False},
        {"source_type": "real_patient"},
        {"clinical_notes": [{"note_type": "fixture", "content": "Synthetic", "synthetic": False}]},
        {"observations": [{"category": "lab", "name": "Empty"}]},
        {"patient_name": "synthetic-rejection-marker"},
    ],
)
def test_api_invalid_input_is_safe_and_atomic(case_client, engine, payload, change):
    response = case_client.post("/api/v1/cases", json=payload | change)
    assert response.status_code == 422
    assert "synthetic-rejection-marker" not in response.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ClinicalCase)) == 0


def test_explicit_deidentification_and_empty_case(case_client, payload):
    payload.pop("deidentified")
    assert case_client.post("/api/v1/cases", json=payload).status_code == 422
    payload.update(
        deidentified=True,
        source_type="deidentified",
        patient_profile=None,
        conditions=[],
        observations=[],
        medications=[],
        allergies=[],
        clinical_notes=[
            {"note_type": "fixture", "content": "De-identified fixture", "synthetic": False}
        ],
    )
    assert case_client.post("/api/v1/cases", json=payload).status_code == 201


def test_database_failure_rolls_back_whole_case(case_client, engine, payload):
    def fail_note_insert(*_):
        raise IntegrityError("safe test statement", {}, Exception("private-test-marker"))

    event.listen(ClinicalNote, "before_insert", fail_note_insert)
    try:
        response = case_client.post("/api/v1/cases", json=payload)
    finally:
        event.remove(ClinicalNote, "before_insert", fail_note_insert)
    assert response.status_code == 500
    assert "private-test-marker" not in response.text
    with Session(engine) as session:
        for model in (
            ClinicalCase,
            PatientProfile,
            Condition,
            Observation,
            Medication,
            Allergy,
            ClinicalNote,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_caller_rollback(session, payload):
    create_case(session, ClinicalCaseCreateRequest.model_validate(payload))
    session.rollback()
    assert session.scalar(select(func.count()).select_from(ClinicalCase)) == 0


def test_profile_one_to_one_and_detail_delete_restriction(session, payload):
    record = create_case(session, ClinicalCaseCreateRequest.model_validate(payload))
    session.commit()
    session.add(PatientProfile(clinical_case_id=record.id, synthetic_patient_id="SYN-P999"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    assert record.patient_profile
    session.delete(record)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    assert session.get(ClinicalCase, record.id) is not None


def test_empty_observation_database_constraint(session, payload):
    record = create_case(session, ClinicalCaseCreateRequest.model_validate(payload))
    session.commit()
    session.add(Observation(clinical_case_id=record.id, category="lab", name="Empty"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_dataset_and_seed_rerun(session):
    cases = load_dataset()
    assert len(cases) == 10
    assert len({c.external_case_id for c in cases}) == 10
    assert len({c.patient_profile.synthetic_patient_id for c in cases}) == 10
    assert all(c.source_type == "synthetic" and c.deidentified for c in cases)
    assert seed_cases(session, cases) == (10, 0)
    session.commit()
    ids = set(session.scalars(select(ClinicalCase.id)))
    assert seed_cases(session, load_dataset()) == (0, 10)
    session.commit()
    assert set(session.scalars(select(ClinicalCase.id))) == ids
    assert session.scalar(select(func.count()).select_from(PatientProfile)) == 10
    assert session.scalar(select(func.count()).select_from(ClinicalNote)) == 10


def test_openapi(app):
    paths = app.openapi()["paths"]
    assert "201" in paths["/api/v1/cases"]["post"]["responses"]
    assert "404" in paths["/api/v1/cases/{case_id}"]["get"]["responses"]
    assert "/health" in paths


def test_duplicate_race_savepoint_keeps_session_usable(session, payload, monkeypatch):
    from backend.app.services import clinical_cases

    request = ClinicalCaseCreateRequest.model_validate(payload)
    create_case(session, request)
    session.commit()
    original = clinical_cases.find_case_id
    calls = 0

    def initially_missing(db, external_id):
        nonlocal calls
        calls += 1
        return None if calls == 1 else original(db, external_id)

    monkeypatch.setattr(clinical_cases, "find_case_id", initially_missing)
    with pytest.raises(clinical_cases.DuplicateCaseError):
        create_case(session, request)
    assert session.scalar(select(func.count()).select_from(ClinicalCase)) == 1
    other = request.model_copy(update={"external_case_id": "CASE-SECOND"})
    create_case(session, other)
    session.commit()
    assert session.scalar(select(func.count()).select_from(ClinicalCase)) == 2


def test_seed_cli_validation_and_rerun(engine, monkeypatch, capsys):
    from scripts import seed_synthetic_cases as seed

    monkeypatch.setattr("sys.argv", ["seed_synthetic_cases", "--validate-only"])
    assert seed.main() == 0
    assert capsys.readouterr().out == "validated 10 synthetic cases\n"
    monkeypatch.setattr(seed, "get_engine", lambda: engine)
    monkeypatch.setattr("sys.argv", ["seed_synthetic_cases"])
    assert seed.main() == 0
    assert capsys.readouterr().out == "inserted 10\nskipped 0\n"
    assert seed.main() == 0
    assert capsys.readouterr().out == "inserted 0\nskipped 10\n"


def test_seed_rejects_invalid_dataset_before_database_use(tmp_path, monkeypatch, capsys):
    from scripts import seed_synthetic_cases as seed

    path = tmp_path / "invalid.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="exactly 10"):
        load_dataset(path)
    monkeypatch.setattr(seed, "load_dataset", lambda: load_dataset(path))
    monkeypatch.setattr("sys.argv", ["seed_synthetic_cases"])
    assert seed.main() == 1
    assert capsys.readouterr().out.startswith("Seed failed;")
