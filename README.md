# OrderFlow Lite

OrderFlow Lite is a compact order and inventory API. Its v1.0 scope covers product
creation, complete pending orders, and confirmation with safe stock accounting. M3
hardens the core flow for concurrent confirmation and duplicate order-creation requests.

## Status

Implemented through M3:

- synchronous FastAPI application with PostgreSQL liveness/readiness probes;
- Product, Order, and OrderItem persistence with database constraints;
- `Decimal`/`NUMERIC(18,2)` money and immutable item price snapshots;
- atomic pending-order creation and derived line/order totals;
- concurrent-safe confirmation using deterministic pessimistic row locking;
- persistent order-creation idempotency with canonical request fingerprints;
- dedicated PostgreSQL integration tests, migrations, lint, typing, and CI.

Planned for M4:

- final hardening and documentation review;
- complete release validation;
- v1.0.0 release preparation.

Post-v1.0 work may revisit capabilities that are explicitly outside the current scope;
none are presented as part of this release line.

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

Compose runs PostgreSQL only. On first initialization it creates `orderflow` for
development and the isolated `orderflow_test` database for tests. PostgreSQL is
published on `127.0.0.1:55432`; the API runs directly on the host.

The example credentials are local-only and are not intended for shared or production
environments. `.env` is ignored by Git.

## Configuration

`APP_ENV` identifies the runtime environment. `DATABASE_URL` is used by the API and
Alembic. `TEST_DATABASE_URL` selects the dedicated test database; the test bootstrap
refuses any database name other than `orderflow_test` before running destructive test
cleanup.

## Migrations

Apply the migration chain to the configured development database:

```bash
uv run alembic upgrade head
```

- `0001_baseline` establishes Alembic without domain tables.
- `0002_core_order_flow` creates `products`, `orders`, and `order_items` with their
  persistent invariants.
- `0003_consistency_idempotency` creates only `idempotency_records` for successful
  order-creation requests.

## Run the API

```bash
uv run uvicorn orderflow.app:app --reload
```

Implemented functional endpoints:

```text
POST /api/v1/products
GET  /api/v1/products/{product_id}
POST /api/v1/orders
GET  /api/v1/orders/{order_id}
POST /api/v1/orders/{order_id}/confirm
```

Operational endpoints:

- `GET /health` reports process liveness without accessing PostgreSQL.
- `GET /ready` executes a minimal PostgreSQL query and returns a sanitized `503` when
  the database is unavailable.

Example product payload:

```json
{
  "sku": "SKU-001",
  "name": "Mechanical Keyboard",
  "unit_price": "349.90",
  "stock_quantity": 5
}
```

Example order payload:

```json
{
  "items": [
    {
      "product_id": "00000000-0000-0000-0000-000000000000",
      "quantity": 2
    }
  ]
}
```

Order creation requires an opaque idempotency key:

```http
POST /api/v1/orders HTTP/1.1
Idempotency-Key: order-create-123
Content-Type: application/json
```

- the first successful request returns `201`;
- the same key and semantically equivalent request return `200` and the same Order;
- the same key with a different request returns `409 IDEMPOTENCY_KEY_REUSED`;
- an attempt that fails before commit does not reserve the key.

Idempotency records are retained indefinitely in v1.0. A replay follows the stored
resource reference and therefore returns the current representation of the Order, not a
stored copy of the original HTTP response.

The client never supplies item prices. Each OrderItem captures the Product price when
the order is created. Line totals and the order total are derived at response time and
are not persisted.

Confirmation runs at PostgreSQL `READ COMMITTED`, locks the Order first, then locks every
referenced Product in ascending Product ID order. Stock is validated for every line
before the atomic debit, preventing overselling and duplicate concurrent confirmation.

## Tests and quality

Keep PostgreSQL running, then execute:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```

Tests use real PostgreSQL rather than SQLite so migrations, constraints, transactions,
and readiness behavior exercise the selected production database engine.

## Delivery phases

- M0 — Scope + Stack: completed
- M1 — Foundation: completed
- M2 — Core Order Flow: completed
- M3 — Consistency + Idempotency: implemented in the current branch
- M4 — Hardening + v1.0.0: planned

There is no M5.

## Out of scope

The current v1.0 scope excludes cancellation, product/order list or update endpoints,
authentication, users, payments, frontend applications, Redis, background workers,
event buses, microservices, deployment automation, and advanced observability.
