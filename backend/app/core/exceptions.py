"""Safe, deliberately small API error contract."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger("medtrust.api")


class MedTrustError(Exception):
    """Base project failure. Exception details are never returned to clients."""


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


async def project_error_handler(request: Request, exc: MedTrustError) -> JSONResponse:
    logger.error("project_error")
    return error_response(500, "medtrust_error", "The request could not be completed.")


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unexpected_server_error")
    return error_response(500, "internal_server_error", "An unexpected server error occurred.")


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    try:
        message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        message = "Request failed."
    response = error_response(exc.status_code, "http_error", message)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(422, "validation_error", "Request validation failed.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(MedTrustError, project_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
