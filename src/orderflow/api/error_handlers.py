"""Small, stable error response foundation for the HTTP API."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    """Machine-readable error payload."""

    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Top-level API error envelope."""

    error: ErrorBody


class ApiError(Exception):
    """Expected API failure that is safe to expose to a client."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


async def api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Render an expected API failure without leaking internal context."""

    if not isinstance(exc, ApiError):
        raise TypeError("api_error_handler received an unexpected exception type")

    payload = ErrorResponse(
        error=ErrorBody(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


async def internal_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures and expose only a generic response."""

    logger.error("Unhandled request error", exc_info=exc)
    payload = ErrorResponse(
        error=ErrorBody(
            code="INTERNAL_ERROR",
            message="An internal error occurred.",
        )
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Render Pydantic/FastAPI validation failures in the common envelope."""

    if not isinstance(exc, RequestValidationError):
        raise TypeError(
            "validation_error_handler received an unexpected exception type"
        )

    errors = [
        {
            "location": list(error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    payload = ErrorResponse(
        error=ErrorBody(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details={"errors": errors},
        )
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    """Register the application's error response handlers."""

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
