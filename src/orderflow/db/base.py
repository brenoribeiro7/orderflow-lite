"""Declarative metadata shared by the domain models and Alembic."""

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""


def utc_now() -> datetime:
    """Return an application-assigned timezone-aware timestamp."""

    return datetime.now(UTC)
