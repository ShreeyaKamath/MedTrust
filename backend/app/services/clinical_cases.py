"""Atomic research-case persistence; no clinical reasoning or external calls."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.models import (
    Allergy,
    ClinicalCase,
    ClinicalNote,
    Condition,
    Medication,
    Observation,
    PatientProfile,
)
from backend.app.schemas.clinical_case import ClinicalCaseCreateRequest

DETAIL_MODELS = {
    "patient_profile": PatientProfile,
    "conditions": Condition,
    "observations": Observation,
    "medications": Medication,
    "allergies": Allergy,
    "clinical_notes": ClinicalNote,
}


class DuplicateCaseError(Exception):
    """An external research case reference already exists."""


def find_case_id(session: Session, external_case_id: str) -> UUID | None:
    return session.scalar(
        select(ClinicalCase.id).where(ClinicalCase.external_case_id == external_case_id)
    )


def create_case(session: Session, request: ClinicalCaseCreateRequest) -> ClinicalCase:
    """Flush one nested case; caller owns commit/rollback of the outer transaction.

    A savepoint isolates duplicate races without discarding other seed inserts.
    """
    if find_case_id(session, request.external_case_id) is not None:
        raise DuplicateCaseError()
    record = ClinicalCase(**request.model_dump(exclude=set(DETAIL_MODELS)))
    for attribute, model in DETAIL_MODELS.items():
        data = getattr(request, attribute)
        value = (
            (model(**data.model_dump()) if data else None)
            if attribute == "patient_profile"
            else [model(**item.model_dump()) for item in data]
        )
        setattr(record, attribute, value)
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
    except IntegrityError:
        if find_case_id(session, request.external_case_id) is not None:
            raise DuplicateCaseError() from None
        raise
    return record


def get_case(session: Session, case_id: UUID) -> ClinicalCase | None:
    return session.scalar(
        select(ClinicalCase)
        .where(ClinicalCase.id == case_id)
        .options(*(selectinload(getattr(ClinicalCase, field)) for field in DETAIL_MODELS))
    )
