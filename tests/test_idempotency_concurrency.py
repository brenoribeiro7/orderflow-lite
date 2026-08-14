"""PostgreSQL unique-key arbitration under concurrent order creation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from threading import Barrier, Lock
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from orderflow.api.error_handlers import ApiError
from orderflow.db.session import SessionFactory
from orderflow.idempotency.model import IdempotencyRecord
from orderflow.orders import service as order_service
from orderflow.orders.model import Order, OrderItem
from orderflow.orders.schemas import OrderCreate
from orderflow.products.model import Product


@dataclass(frozen=True)
class CreationOutcome:
    code: str
    order_id: UUID | None = None
    replayed: bool | None = None


def create_product(*, sku: str) -> UUID:
    with SessionFactory.begin() as session:
        product = Product(
            sku=sku,
            name=f"Product {sku}",
            unit_price=Decimal("10.00"),
            stock_quantity=10,
        )
        session.add(product)
        session.flush()
        return product.id


def order_payload(items: list[tuple[UUID, int]]) -> OrderCreate:
    return OrderCreate.model_validate(
        {
            "items": [
                {"product_id": str(product_id), "quantity": quantity}
                for product_id, quantity in items
            ]
        }
    )


def synchronize_initial_key_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make both transactions observe the absent key before either INSERT."""

    original_lookup = order_service._find_idempotency_record
    barrier = Barrier(2)
    counter_lock = Lock()
    lookup_count = 0

    def synchronized_lookup(
        session: Session,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        nonlocal lookup_count
        record = original_lookup(session, idempotency_key)
        with counter_lock:
            lookup_count += 1
            is_initial_race_lookup = lookup_count <= 2
        if is_initial_race_lookup:
            barrier.wait(timeout=5)
        return record

    monkeypatch.setattr(
        order_service,
        "_find_idempotency_record",
        synchronized_lookup,
    )


def create_concurrently(
    payload: OrderCreate,
    idempotency_key: str,
) -> CreationOutcome:
    with SessionFactory() as session:
        try:
            result = order_service.create_order(session, payload, idempotency_key)
        except ApiError as exc:
            return CreationOutcome(code=exc.code)
        return CreationOutcome(
            code="success",
            order_id=result.order.id,
            replayed=result.replayed,
        )


def run_concurrent_creations(
    first: OrderCreate,
    second: OrderCreate,
    *,
    idempotency_key: str,
) -> list[CreationOutcome]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(create_concurrently, payload, idempotency_key)
            for payload in (first, second)
        ]
        return [future.result(timeout=10) for future in futures]


def persistence_counts() -> tuple[int, int, int]:
    with SessionFactory() as session:
        orders = session.scalar(select(func.count()).select_from(Order))
        items = session.scalar(select(func.count()).select_from(OrderItem))
        records = session.scalar(select(func.count()).select_from(IdempotencyRecord))
        return orders or 0, items or 0, records or 0


def test_concurrent_same_key_and_payload_create_exactly_one_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_a = create_product(sku="RACE-SAME-A")
    product_b = create_product(sku="RACE-SAME-B")
    payload = order_payload([(product_a, 1), (product_b, 2)])
    synchronize_initial_key_lookups(monkeypatch)

    outcomes = run_concurrent_creations(
        payload,
        payload,
        idempotency_key="concurrent-same-payload",
    )

    assert [outcome.code for outcome in outcomes] == ["success", "success"]
    assert sorted(
        outcome.replayed for outcome in outcomes if outcome.replayed is not None
    ) == [
        False,
        True,
    ]
    assert len({outcome.order_id for outcome in outcomes}) == 1
    assert persistence_counts() == (1, 2, 1)


def test_concurrent_same_key_and_different_payload_persists_one_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = create_product(sku="RACE-DIFFERENT")
    first = order_payload([(product, 1)])
    second = order_payload([(product, 2)])
    synchronize_initial_key_lookups(monkeypatch)

    outcomes = run_concurrent_creations(
        first,
        second,
        idempotency_key="concurrent-different-payload",
    )

    assert sorted(outcome.code for outcome in outcomes) == [
        "IDEMPOTENCY_KEY_REUSED",
        "success",
    ]
    assert persistence_counts() == (1, 1, 1)
