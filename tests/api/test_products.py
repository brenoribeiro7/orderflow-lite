"""Product API behavior."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def product_payload(*, sku: str = "SKU-001") -> dict[str, object]:
    return {
        "sku": sku,
        "name": "Mechanical Keyboard",
        "unit_price": "349.90",
        "stock_quantity": 5,
    }


def test_create_and_get_product(client: TestClient) -> None:
    payload = product_payload()
    payload["sku"] = "  SKU-001  "
    payload["name"] = "  Mechanical Keyboard  "

    created = client.post("/api/v1/products", json=payload)

    assert created.status_code == 201
    body = created.json()
    assert body["sku"] == "SKU-001"
    assert body["name"] == "Mechanical Keyboard"
    assert body["unit_price"] == "349.90"
    assert body["stock_quantity"] == 5
    assert body["created_at"]
    assert body["updated_at"]

    fetched = client.get(f"/api/v1/products/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_product_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/products/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_duplicate_sku_is_conflict(client: TestClient) -> None:
    assert client.post("/api/v1/products", json=product_payload()).status_code == 201

    response = client.post("/api/v1/products", json=product_payload())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SKU_ALREADY_EXISTS"


def test_sku_uniqueness_is_case_sensitive(client: TestClient) -> None:
    upper = client.post("/api/v1/products", json=product_payload(sku="Case-SKU"))
    lower = client.post("/api/v1/products", json=product_payload(sku="case-sku"))

    assert upper.status_code == 201
    assert lower.status_code == 201


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unit_price", "-0.01"),
        ("unit_price", "10.999"),
        ("stock_quantity", -1),
        ("name", "   "),
        ("sku", "   "),
    ],
)
def test_product_validation(
    client: TestClient,
    field: str,
    value: object,
) -> None:
    payload = product_payload()
    payload[field] = value

    response = client.post("/api/v1/products", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
