"""Real PostgreSQL concurrency and rollback guarantees for confirmation."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from orderflow.api.error_handlers import ApiError
from orderflow.db.session import SessionFactory
from orderflow.orders import service as order_service
from orderflow.orders.model import Order, OrderStatus
from orderflow.orders.schemas import OrderCreate
from orderflow.products.model import Product


def create_product(*, sku: str, stock: int) -> UUID:
    with SessionFactory.begin() as session:
        product = Product(
            sku=sku,
            name=f"Product {sku}",
            unit_price=Decimal("10.00"),
            stock_quantity=stock,
        )
        session.add(product)
        session.flush()
        return product.id


def create_order(items: list[tuple[UUID, int]]) -> UUID:
    payload = OrderCreate.model_validate(
        {
            "items": [
                {"product_id": str(product_id), "quantity": quantity}
                for product_id, quantity in items
            ]
        }
    )
    with SessionFactory() as session:
        result = order_service.create_order(session, payload, uuid4().hex)
        return result.order.id


def confirm_concurrently(barrier: Barrier, order_id: UUID) -> str:
    barrier.wait(timeout=5)
    with SessionFactory() as session:
        try:
            order_service.confirm_order(session, order_id)
        except ApiError as exc:
            return exc.code
    return "success"


def concurrent_confirmations(order_ids: tuple[UUID, UUID]) -> list[str]:
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(confirm_concurrently, barrier, order_id)
            for order_id in order_ids
        ]
        return [future.result(timeout=10) for future in futures]


def test_engine_uses_explicit_read_committed_isolation() -> None:
    with SessionFactory() as session:
        isolation = cast(
            str,
            session.execute(text("SHOW transaction_isolation")).scalar_one(),
        )

    assert isolation == "read committed"


def test_competing_orders_cannot_oversell_last_unit() -> None:
    product_id = create_product(sku="LAST-UNIT", stock=1)
    order_a = create_order([(product_id, 1)])
    order_b = create_order([(product_id, 1)])

    outcomes = concurrent_confirmations((order_a, order_b))

    assert sorted(outcomes) == ["INSUFFICIENT_STOCK", "success"]
    with SessionFactory() as session:
        product = session.get_one(Product, product_id)
        statuses = session.scalars(
            select(Order.status).where(Order.id.in_([order_a, order_b]))
        ).all()
        assert product.stock_quantity == 0
        assert statuses.count(OrderStatus.CONFIRMED) == 1
        assert statuses.count(OrderStatus.PENDING) == 1


def test_same_order_is_debited_only_once_under_concurrent_confirmation() -> None:
    product_id = create_product(sku="SAME-ORDER", stock=5)
    order_id = create_order([(product_id, 2)])

    outcomes = concurrent_confirmations((order_id, order_id))

    assert sorted(outcomes) == ["ORDER_ALREADY_CONFIRMED", "success"]
    with SessionFactory() as session:
        product = session.get_one(Product, product_id)
        order = session.get_one(Order, order_id)
        assert product.stock_quantity == 3
        assert order.status == OrderStatus.CONFIRMED


def test_multi_product_locks_are_deterministic_for_reversed_inputs() -> None:
    product_a = create_product(sku="LOCK-A", stock=2)
    product_b = create_product(sku="LOCK-B", stock=2)
    order_a = create_order([(product_a, 1), (product_b, 1)])
    order_b = create_order([(product_b, 1), (product_a, 1)])

    outcomes = concurrent_confirmations((order_a, order_b))

    assert outcomes == ["success", "success"]
    with SessionFactory() as session:
        products = {
            product.id: product
            for product in session.scalars(
                select(Product).where(Product.id.in_([product_a, product_b]))
            )
        }
        orders = session.scalars(
            select(Order).where(Order.id.in_([order_a, order_b]))
        ).all()
        assert products[product_a].stock_quantity == 0
        assert products[product_b].stock_quantity == 0
        assert all(order.status == OrderStatus.CONFIRMED for order in orders)


def test_mid_transaction_failure_rolls_back_all_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_a = create_product(sku="ROLLBACK-A", stock=4)
    product_b = create_product(sku="ROLLBACK-B", stock=5)
    order_id = create_order([(product_a, 1), (product_b, 2)])

    def fail_after_stock_mutations() -> None:
        raise RuntimeError("fault injected after stock mutation")

    monkeypatch.setattr(order_service, "utc_now", fail_after_stock_mutations)

    with SessionFactory() as session:
        with pytest.raises(RuntimeError, match="fault injected"):
            order_service.confirm_order(session, order_id)

    with SessionFactory() as verification_session:
        first = verification_session.get_one(Product, product_a)
        second = verification_session.get_one(Product, product_b)
        order = verification_session.get_one(Order, order_id)
        assert first.stock_quantity == 4
        assert second.stock_quantity == 5
        assert order.status == OrderStatus.PENDING
        assert order.confirmed_at is None
