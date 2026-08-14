"""Liveness and database readiness endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from orderflow.api.error_handlers import ApiError, ErrorResponse
from orderflow.db.session import get_db_session

router = APIRouter(tags=["system"])


class StatusResponse(BaseModel):
    """Stable successful probe payload."""

    status: Literal["ok"] = "ok"


@router.get("/health", response_model=StatusResponse)
def health() -> StatusResponse:
    """Report process liveness without consulting PostgreSQL."""

    return StatusResponse()


@router.get(
    "/ready",
    response_model=StatusResponse,
    responses={503: {"model": ErrorResponse}},
)
def ready(session: Annotated[Session, Depends(get_db_session)]) -> StatusResponse:
    """Report readiness after a minimal real PostgreSQL query."""

    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise ApiError(
            status_code=503,
            code="NOT_READY",
            message="Database is not ready.",
        ) from exc

    return StatusResponse()
