"""Order creation, query, confirmation, and rollback behavior."""

from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from orderflow.db.session import SessionFactory
from orderflow.orders.model import Order


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


def create_order(
    client: TestClient,
    items: list[dict[str, object]],
) -> dict[str, object]:
    response = client.post("/api/v1/orders", json={"items": items})
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def test_create_order_snapshots_price_and_preserves_stock(client: TestClient) -> None:
    product = create_product(client, sku="P-1", price="19.99", stock=5)

    order = create_order(
        client,
        [{"product_id": product["id"], "quantity": 3}],
    )

    assert order["status"] == "PENDING"
    assert order["confirmed_at"] is None
    assert order["items"] == [
        {
            "product_id": product["id"],
            "quantity": 3,
            "unit_price": "19.99",
            "line_total": "59.97",
        }
    ]
    assert order["total_amount"] == "59.97"

    product_after = client.get(f"/api/v1/products/{product['id']}").json()
    assert product_after["stock_quantity"] == 5


def test_order_with_multiple_items_has_derived_total(client: TestClient) -> None:
    product_a = create_product(client, sku="P-A", price="10.00")
    product_b = create_product(client, sku="P-B", price="4.50")

    order = create_order(
        client,
        [
            {"product_id": product_a["id"], "quantity": 2},
            {"product_id": product_b["id"], "quantity": 3},
        ],
    )

    assert order["total_amount"] == "33.50"
    response_items = cast(list[dict[str, object]], order["items"])
    assert {item["line_total"] for item in response_items} == {"20.00", "13.50"}


def test_missing_product_rolls_back_entire_order(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": str(uuid4()), "quantity": 1}]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    with SessionFactory() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0


def test_empty_order_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/orders", json={"items": []})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_product_in_order_is_rejected(client: TestClient) -> None:
    product = create_product(client, sku="DUP")
    item = {"product_id": product["id"], "quantity": 1}

    response = client.post("/api/v1/orders", json={"items": [item, item]})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_order_and_order_not_found(client: TestClient) -> None:
    product = create_product(client, sku="GET")
    order = create_order(
        client,
        [{"product_id": product["id"], "quantity": 1}],
    )

    fetched = client.get(f"/api/v1/orders/{order['id']}")
    missing = client.get(f"/api/v1/orders/{uuid4()}")

    assert fetched.status_code == 200
    assert fetched.json() == order
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_confirm_order_debits_stock_and_sets_timestamps(client: TestClient) -> None:
    product = create_product(client, sku="CONFIRM", stock=5)
    order = create_order(
        client,
        [{"product_id": product["id"], "quantity": 2}],
    )

    response = client.post(f"/api/v1/orders/{order['id']}/confirm")

    assert response.status_code == 200
    confirmed = response.json()
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["confirmed_at"] is not None
    assert confirmed["updated_at"] == confirmed["confirmed_at"]
    product_after = client.get(f"/api/v1/products/{product['id']}").json()
    assert product_after["stock_quantity"] == 3


def test_insufficient_stock_preserves_pending_order(client: TestClient) -> None:
    product = create_product(client, sku="LOW", stock=1)
    order = create_order(
        client,
        [{"product_id": product["id"], "quantity": 2}],
    )

    response = client.post(f"/api/v1/orders/{order['id']}/confirm")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert client.get(f"/api/v1/products/{product['id']}").json()["stock_quantity"] == 1
    order_after = client.get(f"/api/v1/orders/{order['id']}").json()
    assert order_after["status"] == "PENDING"
    assert order_after["confirmed_at"] is None


def test_multi_item_insufficiency_causes_no_partial_debit(client: TestClient) -> None:
    product_a = create_product(client, sku="ENOUGH", stock=10)
    product_b = create_product(client, sku="SHORT", stock=3)
    order = create_order(
        client,
        [
            {"product_id": product_a["id"], "quantity": 2},
            {"product_id": product_b["id"], "quantity": 4},
        ],
    )

    response = client.post(f"/api/v1/orders/{order['id']}/confirm")

    assert response.status_code == 409
    assert (
        client.get(f"/api/v1/products/{product_a['id']}").json()["stock_quantity"] == 10
    )
    assert (
        client.get(f"/api/v1/products/{product_b['id']}").json()["stock_quantity"] == 3
    )
    assert client.get(f"/api/v1/orders/{order['id']}").json()["status"] == "PENDING"


def test_second_confirmation_does_not_debit_twice(client: TestClient) -> None:
    product = create_product(client, sku="ONCE", stock=5)
    order = create_order(
        client,
        [{"product_id": product["id"], "quantity": 2}],
    )

    first = client.post(f"/api/v1/orders/{order['id']}/confirm")
    second = client.post(f"/api/v1/orders/{order['id']}/confirm")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ORDER_ALREADY_CONFIRMED"
    assert client.get(f"/api/v1/products/{product['id']}").json()["stock_quantity"] == 3


def test_confirm_missing_order(client: TestClient) -> None:
    response = client.post(f"/api/v1/orders/{uuid4()}/confirm")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_complete_order_flow(client: TestClient) -> None:
    product_a = create_product(client, sku="E2E-A", price="12.50", stock=6)
    product_b = create_product(client, sku="E2E-B", price="7.25", stock=4)
    order = create_order(
        client,
        [
            {"product_id": product_a["id"], "quantity": 2},
            {"product_id": product_b["id"], "quantity": 1},
        ],
    )

    assert client.get(f"/api/v1/orders/{order['id']}").json()["status"] == "PENDING"
    assert (
        client.get(f"/api/v1/products/{product_a['id']}").json()["stock_quantity"] == 6
    )
    assert (
        client.get(f"/api/v1/products/{product_b['id']}").json()["stock_quantity"] == 4
    )

    confirmed = client.post(f"/api/v1/orders/{order['id']}/confirm")

    assert confirmed.status_code == 200
    assert client.get(f"/api/v1/orders/{order['id']}").json()["status"] == "CONFIRMED"
    assert (
        client.get(f"/api/v1/products/{product_a['id']}").json()["stock_quantity"] == 4
    )
    assert (
        client.get(f"/api/v1/products/{product_b['id']}").json()["stock_quantity"] == 3
    )
    assert UUID(cast(str, order["id"]))
