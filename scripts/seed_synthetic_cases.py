"""Load committed synthetic fixtures via python -m scripts.seed_synthetic_cases."""

import argparse
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.session import get_engine
from backend.app.models.enums import CaseSourceType
from backend.app.schemas.clinical_case import ClinicalCaseCreateRequest
from backend.app.services.clinical_cases import DuplicateCaseError, create_case

DATASET = Path(__file__).resolve().parents[1] / "datasets/synthetic/clinical_cases.json"


def load_dataset(path: Path = DATASET) -> list[ClinicalCaseCreateRequest]:
    cases = TypeAdapter(list[ClinicalCaseCreateRequest]).validate_json(path.read_text())
    if len(cases) != 10 or len({case.external_case_id for case in cases}) != 10:
        raise ValueError("Dataset must contain exactly 10 unique cases")
    patient_ids = set()
    for case in cases:
        if case.source_type != CaseSourceType.SYNTHETIC or case.patient_profile is None:
            raise ValueError("Seed cases must be synthetic with a synthetic profile")
        patient_ids.add(case.patient_profile.synthetic_patient_id)
    if len(patient_ids) != 10:
        raise ValueError("Seed patient identifiers must be unique")
    return cases


def seed_cases(session: Session, cases: list[ClinicalCaseCreateRequest]) -> tuple[int, int]:
    """Caller commits the batch. Existing external references are skipped, never updated."""
    inserted = skipped = 0
    for case in cases:
        try:
            create_case(session, case)
            inserted += 1
        except DuplicateCaseError:
            skipped += 1
    return inserted, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only", action="store_true", help="Validate without database access"
    )
    args = parser.parse_args()
    try:
        cases = load_dataset()
        if args.validate_only:
            print(f"validated {len(cases)} synthetic cases")
            return 0
        engine = get_engine()
        try:
            with Session(engine) as session, session.begin():
                inserted, skipped = seed_cases(session, cases)
            print(f"inserted {inserted}\nskipped {skipped}")
        finally:
            engine.dispose()
    except (OSError, ValueError, ValidationError, RuntimeError, SQLAlchemyError):
        # Validation errors and SQL errors may embed input or credentials.
        print("Seed failed; verify dataset, database configuration and migration state.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
