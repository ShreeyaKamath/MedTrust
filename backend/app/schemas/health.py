"""Public liveness response; no infrastructure inventory or secrets."""

from typing import Literal

from pydantic import BaseModel

from backend.app.core.config import Environment


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["medtrust-api"] = "medtrust-api"
    environment: Environment
    version: str
