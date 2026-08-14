# Architecture

## Current foundation

OrderFlow Lite is a small modular monolith using synchronous FastAPI, synchronous
SQLAlchemy `Session` objects, and PostgreSQL. The API runs on the host while Docker
Compose runs only PostgreSQL. M1 implements infrastructure and probes; it does not
implement domain models or order behavior.

Each request or use case receives its own SQLAlchemy `Session`. The FastAPI dependency
closes the session but never commits it. Future transactional use cases will own their
commit and rollback boundaries. `pool_pre_ping` avoids handing stale pooled connections
to a request.

## Approved target flow

The following is an M0 decision reserved for M2/M3 implementation:

```text
create product
→ create PENDING order with all items
→ confirm
→ debit stock atomically
→ CONFIRMED
```

Orders have two target states: `PENDING` and `CONFIRMED`.

Money will use `Decimal` in Python and `NUMERIC(18,2)` in PostgreSQL. `OrderItem` will
store a price snapshot so later product price changes do not rewrite order history.

## Future confirmation transaction

The approved confirmation sequence, not yet implemented, is:

```text
order FOR UPDATE
→ products ordered by id FOR UPDATE
→ validate stock
→ decrement stock
→ mark confirmed
→ commit
```

Concurrency will use PostgreSQL `READ COMMITTED` together with pessimistic row locking.
Ordering product locks by identifier provides a consistent acquisition order.

## Future idempotency

Idempotency is planned only for `POST /api/v1/orders`. It will use `Idempotency-Key`, a
SHA-256 fingerprint of the canonical request, a database unique constraint, and a
reference to the created resource. No idempotency implementation exists in M1.

## Scope boundaries

M1 excludes Product, Order, OrderItem, and IdempotencyRecord models; product and order
endpoints; totals; stock behavior; functional row locking; and business-schema
migrations. The broader v1.0 excludes authentication, users, payments, frontends,
Redis, workers, event buses, microservices, and deployment.
