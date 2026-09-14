"""Local synthetic/de-identified research case intake and retrieval."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.clinical_case import ClinicalCaseCreateRequest, ClinicalCaseDetailResponse
from backend.app.services.clinical_cases import DuplicateCaseError, create_case, get_case

router = APIRouter(prefix="/api/v1/cases", tags=["research cases"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=ClinicalCaseDetailResponse,
    status_code=201,
    summary="Create a synthetic or de-identified research case",
    description="Stores supplied research artifacts without generating medical recommendations.",
    responses={409: {"description": "External case identifier already exists"}},
)
def create_research_case(request: ClinicalCaseCreateRequest, session: DatabaseSession):
    try:
        record = create_case(session, request)
        response = ClinicalCaseDetailResponse.model_validate(record)
        session.commit()
        return response
    except DuplicateCaseError:
        session.rollback()
        raise HTTPException(status_code=409) from None


@router.get(
    "/{case_id}",
    response_model=ClinicalCaseDetailResponse,
    summary="Retrieve a structured research case",
    description="Returns case metadata and details as research artifacts, without EHR authority.",
    responses={404: {"description": "Research case not found"}},
)
def retrieve_research_case(case_id: UUID, session: DatabaseSession):
    record = get_case(session, case_id)
    if record is None:
        raise HTTPException(status_code=404)
    return record
