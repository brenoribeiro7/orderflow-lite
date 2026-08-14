# Architecture

## Architecture style

OrderFlow Lite is a small modular monolith using synchronous FastAPI, synchronous
SQLAlchemy `Session` objects, and PostgreSQL. The API runs on the host while Docker
Compose runs only PostgreSQL.

Each request or use case receives its own SQLAlchemy Session. The FastAPI dependency
closes the session but never commits it. Write services own their transaction boundaries;
routers handle HTTP contracts and response mapping. No repository framework hides
SQLAlchemy.

## Implemented through M3

The relational domain consists of Product, Order, and OrderItem. Orders have exactly two
states: `PENDING` and `CONFIRMED`. A database constraint keeps `confirmed_at` null only
for pending orders and non-null only for confirmed orders.

Money uses `Decimal` in Python and `NUMERIC(18,2)` in PostgreSQL. The consumer never
supplies an item price: `OrderItem.unit_price` captures `Product.unit_price` when the
order is created. `line_total` and `total_amount` are derived from snapshots and are not
persisted.

Order creation atomically loads every referenced Product, rejects missing or duplicated
products, and writes the pending Order with every OrderItem. It does not change stock.
The same transaction stores an IdempotencyRecord for the mandatory `Idempotency-Key`.

## Confirmation transaction

Confirmation runs in one service-owned `READ COMMITTED` transaction:

```text
lock Order FOR UPDATE
→ require PENDING
→ load immutable OrderItems
→ lock Products by Product.id ASC FOR UPDATE
→ validate every stock quantity
→ debit all products
→ mark CONFIRMED and set confirmed_at/updated_at
→ commit
```

The lock order is always:

```text
Order
→ Products sorted by Product.id
```

Locking the Order before checking its state prevents two confirmations from observing the
same pending state. Ordering Product locks avoids payload-dependent acquisition order,
while validating every stock quantity before mutation prevents partial debit. Any error
before commit rolls the whole operation back.

No optimistic version column, conditional stock update, advisory lock, automatic retry,
or stronger isolation level is combined with this strategy.

## Order creation idempotency

Idempotency applies only to `POST /api/v1/orders`. The fingerprint is derived solely from
the validated client payload: canonical UUIDs and integer quantities are sorted by
Product ID, serialized as deterministic JSON, and hashed with SHA-256. Price, stock,
timestamps, status, database state, and the key itself are excluded.

The IdempotencyRecord primary key is the concurrency arbiter. A unique-key loser fully
rolls back its attempted Order before opening a new transaction to load the winner:

```text
same key + same fingerprint → replay
same key + different fingerprint → 409 conflict
```

The record stores a resource reference rather than a response body, so replay returns
the current representation of the same Order, including a later confirmation. Failed
attempts leave no record. Retention is indefinite in v1.0; there is no expiration or
cleanup process.

## Scope boundaries

M3 excludes optimistic locking, conditional stock updates, deadlock retries, generic
idempotency middleware, expiration or cleanup, cancellation, restocking, list or update
endpoints, authentication, users, payments, frontends, Redis, workers, event buses,
microservices, and deployment.
