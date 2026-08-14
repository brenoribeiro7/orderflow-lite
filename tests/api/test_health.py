"""HTTP probe behavior."""

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orderflow.app import app
from orderflow.db.session import get_db_session


def test_health_is_independent_from_database(client: TestClient) -> None:
    def database_dependency_must_not_run() -> Iterator[Session]:
        raise AssertionError("The health endpoint must not access the database.")

    app.dependency_overrides[get_db_session] = database_dependency_must_not_run
    try:
        response = client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_with_available_database(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_with_unavailable_database(client: TestClient) -> None:
    def unavailable_database_session() -> Iterator[Session]:
        unavailable_engine = create_engine(
            "postgresql+psycopg://unavailable:unavailable@127.0.0.1:1/"
            "unavailable?connect_timeout=1"
        )
        try:
            with Session(unavailable_engine) as session:
                yield session
        finally:
            unavailable_engine.dispose()

    app.dependency_overrides[get_db_session] = unavailable_database_session
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "NOT_READY",
            "message": "Database is not ready.",
            "details": {},
        }
    }


def test_unexpected_error_is_sanitized() -> None:
    def failing_database_dependency() -> Iterator[Session]:
        raise RuntimeError("sensitive internal context")

    app.dependency_overrides[get_db_session] = failing_database_dependency
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred.",
            "details": {},
        }
    }
    assert "sensitive internal context" not in response.text
