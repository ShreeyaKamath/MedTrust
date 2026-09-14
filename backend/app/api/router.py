"""Central API route registration."""

from fastapi import APIRouter

from backend.app.api.routes.cases import router as cases_router
from backend.app.api.routes.health import router as health_router

router = APIRouter()
router.include_router(health_router)
router.include_router(cases_router)
