"""Synchronous SQLAlchemy engine and request-scoped session lifecycle."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from orderflow.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    isolation_level="READ COMMITTED",
)
SessionFactory = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_db_session() -> Iterator[Session]:
    """Provide one Session and always close it after the request.

    This dependency deliberately does not commit. Transaction boundaries belong to
    the use case that owns the future write operation.
    """

    with SessionFactory() as session:
        yield session
