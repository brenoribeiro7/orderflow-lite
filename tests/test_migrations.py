"""Alembic integration against the dedicated PostgreSQL test database."""

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from orderflow.db.session import engine


def test_alembic_reaches_head() -> None:
    configuration = Config("alembic.ini")
    command.upgrade(configuration, "head")

    script = ScriptDirectory.from_config(configuration)
    with engine.connect() as connection:
        current_heads = MigrationContext.configure(connection).get_current_heads()

    assert set(current_heads) == set(script.get_heads())
