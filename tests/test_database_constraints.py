"""Direct PostgreSQL checks for persistent domain invariants."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from orderflow.db.session import SessionFactory


def now() -> datetime:
    return datetime.now(UTC)


def constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return cast(str | None, getattr(diagnostic, "constraint_name", None))


def assert_constraint_violation(
    statement: str,
    parameters: dict[str, object],
    *,
    expected_constraint: str | None = None,
) -> None:
    with SessionFactory() as session:
        with pytest.raises(IntegrityError) as captured:
            session.execute(text(statement), parameters)
            session.commit()

    if expected_constraint is not None:
        assert constraint_name(captured.value) == expected_constraint


def product_parameters(**overrides: object) -> dict[str, object]:
    parameters: dict[str, object] = {
        "id": uuid4(),
        "sku": f"SKU-{uuid4()}",
        "name": "Product",
        "unit_price": Decimal("10.00"),
        "stock_quantity": 1,
        "created_at": now(),
        "updated_at": now(),
    }
    parameters.update(overrides)
    return parameters


def insert_product(parameters: dict[str, object]) -> None:
    with SessionFactory.begin() as session:
        session.execute(
            text(
                "INSERT INTO products "
                "(id, sku, name, unit_price, stock_quantity, created_at, updated_at) "
                "VALUES (:id, :sku, :name, :unit_price, :stock_quantity, "
                ":created_at, :updated_at)"
            ),
            parameters,
        )


def insert_order(order_id: object, *, status: str = "PENDING") -> None:
    confirmed_at = now() if status == "CONFIRMED" else None
    with SessionFactory.begin() as session:
        session.execute(
            text(
                "INSERT INTO orders "
                "(id, status, created_at, updated_at, confirmed_at) "
                "VALUES (:id, :status, :created_at, :updated_at, :confirmed_at)"
            ),
            {
                "id": order_id,
                "status": status,
                "created_at": now(),
                "updated_at": now(),
                "confirmed_at": confirmed_at,
            },
        )


def test_unique_product_sku_constraint() -> None:
    first = product_parameters(sku="UNIQUE")
    second = product_parameters(sku="UNIQUE")
    insert_product(first)

    assert_constraint_violation(
        "INSERT INTO products "
        "(id, sku, name, unit_price, stock_quantity, created_at, updated_at) "
        "VALUES (:id, :sku, :name, :unit_price, :stock_quantity, "
        ":created_at, :updated_at)",
        second,
        expected_constraint="uq_products_sku",
    )


@pytest.mark.parametrize(
    ("overrides", "expected_constraint"),
    [
        (
            {"unit_price": Decimal("-0.01")},
            "ck_products_unit_price_nonnegative",
        ),
        ({"stock_quantity": -1}, "ck_products_stock_quantity_nonnegative"),
    ],
)
def test_product_nonnegative_constraints(
    overrides: dict[str, object],
    expected_constraint: str,
) -> None:
    assert_constraint_violation(
        "INSERT INTO products "
        "(id, sku, name, unit_price, stock_quantity, created_at, updated_at) "
        "VALUES (:id, :sku, :name, :unit_price, :stock_quantity, "
        ":created_at, :updated_at)",
        product_parameters(**overrides),
        expected_constraint=expected_constraint,
    )


def test_order_status_must_be_valid() -> None:
    assert_constraint_violation(
        "INSERT INTO orders (id, status, created_at, updated_at, confirmed_at) "
        "VALUES (:id, 'INVALID', :created_at, :updated_at, NULL)",
        {"id": uuid4(), "created_at": now(), "updated_at": now()},
    )


def test_order_status_and_confirmed_at_must_be_coherent() -> None:
    assert_constraint_violation(
        "INSERT INTO orders (id, status, created_at, updated_at, confirmed_at) "
        "VALUES (:id, 'PENDING', :created_at, :updated_at, :confirmed_at)",
        {
            "id": uuid4(),
            "created_at": now(),
            "updated_at": now(),
            "confirmed_at": now(),
        },
        expected_constraint="ck_orders_status_confirmed_at_coherent",
    )


@pytest.mark.parametrize(
    ("quantity", "unit_price", "expected_constraint"),
    [
        (0, Decimal("1.00"), "ck_order_items_quantity_positive"),
        (1, Decimal("-0.01"), "ck_order_items_unit_price_nonnegative"),
    ],
)
def test_order_item_value_constraints(
    quantity: int,
    unit_price: Decimal,
    expected_constraint: str,
) -> None:
    product = product_parameters()
    order_id = uuid4()
    insert_product(product)
    insert_order(order_id)

    assert_constraint_violation(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
        "VALUES (:order_id, :product_id, :quantity, :unit_price)",
        {
            "order_id": order_id,
            "product_id": product["id"],
            "quantity": quantity,
            "unit_price": unit_price,
        },
        expected_constraint=expected_constraint,
    )


def test_order_item_composite_primary_key() -> None:
    product = product_parameters()
    order_id = uuid4()
    insert_product(product)
    insert_order(order_id)
    parameters = {
        "order_id": order_id,
        "product_id": product["id"],
        "quantity": 1,
        "unit_price": Decimal("10.00"),
    }

    with SessionFactory.begin() as session:
        session.execute(
            text(
                "INSERT INTO order_items "
                "(order_id, product_id, quantity, unit_price) "
                "VALUES (:order_id, :product_id, :quantity, :unit_price)"
            ),
            parameters,
        )
    assert_constraint_violation(
        "INSERT INTO order_items "
        "(order_id, product_id, quantity, unit_price) "
        "VALUES (:order_id, :product_id, :quantity, :unit_price)",
        parameters,
        expected_constraint="pk_order_items",
    )


def test_order_item_product_foreign_key() -> None:
    order_id = uuid4()
    insert_order(order_id)

    assert_constraint_violation(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
        "VALUES (:order_id, :product_id, 1, 1.00)",
        {"order_id": order_id, "product_id": uuid4()},
        expected_constraint="fk_order_items_product_id_products",
    )


def test_order_item_order_foreign_key() -> None:
    product = product_parameters()
    insert_product(product)

    assert_constraint_violation(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
        "VALUES (:order_id, :product_id, 1, 1.00)",
        {"order_id": uuid4(), "product_id": product["id"]},
        expected_constraint="fk_order_items_order_id_orders",
    )
