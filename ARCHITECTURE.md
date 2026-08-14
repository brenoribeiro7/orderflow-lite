# Architecture

## Architecture style

OrderFlow Lite is a small modular monolith using synchronous FastAPI, synchronous
SQLAlchemy `Session` objects, and PostgreSQL. The API runs on the host while Docker
Compose runs only PostgreSQL.

Each request or use case receives its own SQLAlchemy Session. The FastAPI dependency
closes the session but never commits it. Write services own their transaction boundaries;
routers handle HTTP contracts and response mapping. No repository framework hides
SQLAlchemy.

## Implemented in M2

The relational domain consists of Product, Order, and OrderItem. Orders have exactly two
states: `PENDING` and `CONFIRMED`. A database constraint keeps `confirmed_at` null only
for pending orders and non-null only for confirmed orders.

Money uses `Decimal` in Python and `NUMERIC(18,2)` in PostgreSQL. The consumer never
supplies an item price: `OrderItem.unit_price` captures `Product.unit_price` when the
order is created. `line_total` and `total_amount` are derived from snapshots and are not
persisted.

Order creation atomically loads every referenced Product, rejects missing or duplicated
products, and writes the pending Order with every OrderItem. It does not change stock.

Sequential confirmation runs in one service-owned transaction:

```text
load order and items
→ require PENDING
→ load referenced products
→ validate every stock quantity
→ debit all products
→ mark CONFIRMED and set confirmed_at/updated_at
→ commit
```

Validating every product before the first mutation prevents partial stock debit when one
line is insufficient. A repeated confirmation is rejected before another debit.

## Reserved for M3

M2 deliberately performs no pessimistic or optimistic locking. Its confirmation is
transactionally correct for sequential execution but is not yet hardened against
concurrent stock consumption.

The approved M3 confirmation strategy remains:

```text
order FOR UPDATE
→ products ordered by id FOR UPDATE
→ validate stock
→ decrement stock
→ mark confirmed
→ commit
```

Concurrency will use PostgreSQL `READ COMMITTED` together with pessimistic row locking.
M3 will prove behavior when concurrent requests compete for the final stock unit.

Order creation idempotency is also reserved for M3. The approved design applies only to
`POST /api/v1/orders` and uses a mandatory `Idempotency-Key`, a SHA-256 canonical request
fingerprint, an IdempotencyRecord with database unique arbitration, replay behavior, and
a reference to the created resource. None of that is part of the implemented M2
contract.

## Scope boundaries

M2 excludes `SELECT ... FOR UPDATE`, optimistic locking, conditional stock updates,
deadlock retries, idempotency records or middleware, cancellation, restocking, list or
update endpoints, authentication, users, payments, frontends, Redis, workers, event
buses, microservices, and deployment.
