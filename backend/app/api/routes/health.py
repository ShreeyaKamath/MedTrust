"""Service-independent liveness endpoint."""

from fastapi import APIRouter, Request

from backend.app import __version__
from backend.app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health(request: Request) -> HealthResponse:
    return HealthResponse(environment=request.app.state.settings.env, version=__version__)
