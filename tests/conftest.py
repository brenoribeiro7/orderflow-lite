"""Shared test configuration backed by a dedicated PostgreSQL database."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://orderflow:orderflow@127.0.0.1:55432/orderflow_test"
)


def require_recognized_test_database(database_url: str) -> None:
    """Refuse to let test migration/cleanup utilities target another database."""

    database_name = make_url(database_url).database
    if database_name != "orderflow_test":
        raise RuntimeError(
            "Tests require the dedicated 'orderflow_test' PostgreSQL database."
        )


test_database_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
require_recognized_test_database(test_database_url)

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = test_database_url

from orderflow.app import app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Provide an in-process HTTP client for the application."""

    with TestClient(app) as test_client:
        yield test_client
