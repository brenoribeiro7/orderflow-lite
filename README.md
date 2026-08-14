# OrderFlow Lite

OrderFlow Lite is a compact order and inventory API whose v1.0 scope focuses on
creating products, assembling pending orders, and confirming orders with safe stock
updates. The current repository contains the reproducible application and database
foundation; the order flow itself is planned for later phases.

## Status

Implemented in M1:

- synchronous FastAPI application with `/health` and PostgreSQL-backed `/ready`;
- synchronous SQLAlchemy engine and request-scoped `Session` lifecycle;
- Alembic integration with a no-op baseline revision;
- PostgreSQL 18.6 development and test databases through Docker Compose;
- pytest, Ruff, mypy, and GitHub Actions foundations.

Planned for M2/M3:

- product creation and stock representation;
- complete pending-order creation and confirmation;
- atomic stock debit, price snapshots, and order totals;
- idempotent order creation and concurrency controls.

## Stack

- Python 3.14.6 and uv 0.12.4
- FastAPI, Pydantic, and pydantic-settings
- synchronous SQLAlchemy 2.0, Alembic, and Psycopg 3
- PostgreSQL 18.6
- pytest/HTTPX, Ruff, and mypy

## Requirements

- Git
- uv 0.12.4
- Docker with Docker Compose

Python 3.14.6 can be installed and managed by uv.

## Local setup

```bash
uv python install 3.14.6
uv sync --locked --all-groups
cp .env.example .env
docker compose up -d
docker compose ps
```

The Compose project runs PostgreSQL only. On the first initialization it creates
`orderflow` for development and the isolated `orderflow_test` database for tests.
PostgreSQL is published on `127.0.0.1:55432`; the API runs directly on the host.

The example credentials are local-only and are not intended for shared or production
environments. `.env` is ignored by Git.

## Configuration

`APP_ENV` identifies the runtime environment. `DATABASE_URL` is used by the API and
Alembic. `TEST_DATABASE_URL` selects the dedicated test database; the test bootstrap
refuses any database name other than `orderflow_test`.

## Migrations

Apply all migrations to the configured development database:

```bash
uv run alembic upgrade head
```

The M1 `0001_baseline` revision intentionally creates no domain tables. It establishes
the migration chain so that the M2 schema can be introduced explicitly.

## Run the API

```bash
uv run uvicorn orderflow.app:app --reload
```

- `GET /health` reports process liveness and does not access PostgreSQL.
- `GET /ready` executes a minimal PostgreSQL query, returning `200` when ready and a
  sanitized `503` response when the database is unavailable.

## Tests and quality

Keep PostgreSQL running, then execute:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```

Tests use real PostgreSQL rather than SQLite so migration and readiness behavior match
the production database engine.

## Delivery phases

- M0 — Scope + Stack: completed
- M1 — Foundation: implemented in this repository state
- M2 — Core Order Flow: planned
- M3 — Consistency + Idempotency: planned
- M4 — Hardening + v1.0.0: planned

There is no M5.

## Out of scope

The v1.0 scope excludes authentication, users, payments, frontend applications,
Redis, background workers, event buses, microservices, deployment automation, and
advanced observability.
