"""Declarative metadata shared by future domain models and Alembic."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""
