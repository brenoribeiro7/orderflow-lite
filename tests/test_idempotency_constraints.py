"""Direct PostgreSQL constraints for IdempotencyRecord."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from orderflow.db.session import SessionFactory
from orderflow.orders import service as order_service
from orderflow.orders.model import Order, OrderStatus


def create_order() -> UUID:
    with SessionFactory.begin() as session:
        order = Order(status=OrderStatus.PENDING)
        session.add(order)
        session.flush()
        return order.id


def insert_record(
    *,
    key: str,
    order_id: UUID,
    request_hash: str | None = "a" * 64,
    created_at: datetime | None = None,
) -> None:
    with SessionFactory.begin() as session:
        session.execute(
            text(
                "INSERT INTO idempotency_records "
                "(key, request_hash, order_id, created_at) "
                "VALUES (:key, :request_hash, :order_id, :created_at)"
            ),
            {
                "key": key,
                "request_hash": request_hash,
                "order_id": order_id,
                "created_at": created_at or datetime.now(UTC),
            },
        )


def constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return cast(str | None, getattr(diagnostic, "constraint_name", None))


def column_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return cast(str | None, getattr(diagnostic, "column_name", None))


def capture_violation(
    *,
    key: str,
    order_id: UUID,
    request_hash: str | None = "a" * 64,
    created_at: datetime | None = None,
) -> IntegrityError:
    try:
        insert_record(
            key=key,
            order_id=order_id,
            request_hash=request_hash,
            created_at=created_at,
        )
    except IntegrityError as exc:
        return exc
    raise AssertionError("Expected PostgreSQL to reject the record")


def test_idempotency_key_primary_key_constraint() -> None:
    insert_record(key="same-key", order_id=create_order())

    violation = capture_violation(key="same-key", order_id=create_order())

    assert constraint_name(violation) == "pk_idempotency_records"
    assert order_service._is_idempotency_key_violation(violation)


def test_idempotency_order_id_unique_constraint() -> None:
    order_id = create_order()
    insert_record(key="first-key", order_id=order_id)

    violation = capture_violation(key="second-key", order_id=order_id)

    assert constraint_name(violation) == "uq_idempotency_records_order_id"
    assert not order_service._is_idempotency_key_violation(violation)


def test_idempotency_order_id_foreign_key_constraint() -> None:
    violation = capture_violation(key="missing-order", order_id=uuid4())

    assert constraint_name(violation) == "fk_idempotency_records_order_id_orders"


def test_idempotency_request_hash_is_not_null() -> None:
    violation = capture_violation(
        key="null-hash",
        order_id=create_order(),
        request_hash=None,
    )

    assert column_name(violation) == "request_hash"


def test_idempotency_created_at_is_not_null() -> None:
    order_id = create_order()
    try:
        with SessionFactory.begin() as session:
            session.execute(
                text(
                    "INSERT INTO idempotency_records "
                    "(key, request_hash, order_id, created_at) "
                    "VALUES ('null-created-at', :request_hash, :order_id, NULL)"
                ),
                {"request_hash": "a" * 64, "order_id": order_id},
            )
    except IntegrityError as exc:
        violation = exc
    else:
        raise AssertionError("Expected PostgreSQL to reject a null created_at")

    assert column_name(violation) == "created_at"
