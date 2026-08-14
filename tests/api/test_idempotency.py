"""HTTP contract for persistent order-creation idempotency."""

from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from orderflow.db.session import SessionFactory
from orderflow.idempotency.model import IdempotencyRecord
from orderflow.orders.model import Order
from orderflow.products.model import Product


def create_product(
    client: TestClient,
    *,
    sku: str,
    price: str = "10.00",
    stock: int = 5,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/products",
        json={
            "sku": sku,
            "name": f"Product {sku}",
            "unit_price": price,
            "stock_quantity": stock,
        },
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def order_payload(items: list[tuple[object, int]]) -> dict[str, object]:
    return {
        "items": [
            {"product_id": str(product_id), "quantity": quantity}
            for product_id, quantity in items
        ]
    }


def assert_persistence_counts(*, orders: int, records: int) -> None:
    with SessionFactory() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == orders
        assert (
            session.scalar(select(func.count()).select_from(IdempotencyRecord))
            == records
        )


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Idempotency-Key": "a" * 129},
        {"Idempotency-Key": "abc def"},
    ],
)
def test_idempotency_key_is_required_and_structurally_valid(
    client: TestClient,
    headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/orders",
        json=order_payload([(uuid4(), 1)]),
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert_persistence_counts(orders=0, records=0)


def test_first_request_creates_and_same_request_replays(client: TestClient) -> None:
    product = create_product(client, sku="IDEMPOTENT")
    payload = order_payload([(product["id"], 2)])
    headers = {"Idempotency-Key": "same-request"}

    first = client.post("/api/v1/orders", json=payload, headers=headers)
    replay = client.post("/api/v1/orders", json=payload, headers=headers)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert_persistence_counts(orders=1, records=1)


def test_reordered_items_replay_the_same_order(client: TestClient) -> None:
    product_a = create_product(client, sku="ORDER-A")
    product_b = create_product(client, sku="ORDER-B")
    headers = {"Idempotency-Key": "reordered-items"}

    first = client.post(
        "/api/v1/orders",
        json=order_payload([(product_a["id"], 1), (product_b["id"], 2)]),
        headers=headers,
    )
    replay = client.post(
        "/api/v1/orders",
        json=order_payload([(product_b["id"], 2), (product_a["id"], 1)]),
        headers=headers,
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert_persistence_counts(orders=1, records=1)


def test_same_key_with_different_payload_is_conflict(client: TestClient) -> None:
    product = create_product(client, sku="CONFLICT")
    headers = {"Idempotency-Key": "different-request"}

    first = client.post(
        "/api/v1/orders",
        json=order_payload([(product["id"], 1)]),
        headers=headers,
    )
    conflict = client.post(
        "/api/v1/orders",
        json=order_payload([(product["id"], 2)]),
        headers=headers,
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json() == {
        "error": {
            "code": "IDEMPOTENCY_KEY_REUSED",
            "message": "Idempotency-Key was already used with a different request.",
            "details": {},
        }
    }
    assert_persistence_counts(orders=1, records=1)


def test_failed_attempt_does_not_reserve_key_and_can_retry(client: TestClient) -> None:
    product_id = uuid4()
    payload = order_payload([(product_id, 1)])
    headers = {"Idempotency-Key": "retry-after-failure"}

    failed = client.post("/api/v1/orders", json=payload, headers=headers)

    assert failed.status_code == 404
    assert failed.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert_persistence_counts(orders=0, records=0)

    with SessionFactory.begin() as session:
        session.add(
            Product(
                id=product_id,
                sku="RETRY-PRODUCT",
                name="Retry Product",
                unit_price=Decimal("10.00"),
                stock_quantity=1,
            )
        )

    retried = client.post("/api/v1/orders", json=payload, headers=headers)

    assert retried.status_code == 201
    assert_persistence_counts(orders=1, records=1)


def test_replay_after_confirmation_returns_current_order(client: TestClient) -> None:
    product = create_product(client, sku="CURRENT-RESOURCE", stock=3)
    payload = order_payload([(product["id"], 1)])
    headers = {"Idempotency-Key": "replay-current-resource"}
    created = client.post("/api/v1/orders", json=payload, headers=headers)
    order_id = cast(str, created.json()["id"])

    confirmed = client.post(f"/api/v1/orders/{order_id}/confirm")
    replay = client.post("/api/v1/orders", json=payload, headers=headers)

    assert created.status_code == 201
    assert confirmed.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["id"] == order_id
    assert replay.json()["status"] == "CONFIRMED"
    assert UUID(order_id)
    assert_persistence_counts(orders=1, records=1)
