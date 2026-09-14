"""FastAPI entry point: backend.app.main:app."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app import __version__
from backend.app.api.router import router
from backend.app.core.config import Settings, get_settings
from backend.app.core.exceptions import register_exception_handlers
from backend.app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct an isolated application without contacting external services."""
    settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level)
        yield

    application = FastAPI(
        title="MedTrust API",
        version=__version__,
        description=(
            "Research prototype for clinician-facing clinical decision support. "
            "Infrastructure only; not an autonomous doctor, diagnostic or prescribing "
            "system, or production medical device. No medical recommendations."
        ),
        debug=False,
        lifespan=lifespan,
    )
    application.state.settings = settings
    register_exception_handlers(application)
    application.include_router(router)
    return application


app = create_app()
