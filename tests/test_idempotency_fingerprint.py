"""Semantic properties of canonical order request fingerprints."""

import re
from uuid import UUID

from orderflow.idempotency.fingerprint import order_request_fingerprint
from orderflow.orders.schemas import OrderCreate

PRODUCT_A = UUID("00000000-0000-0000-0000-000000000001")
PRODUCT_B = UUID("00000000-0000-0000-0000-000000000002")
PRODUCT_C = UUID("00000000-0000-0000-0000-000000000003")


def order_payload(items: list[tuple[UUID, int]]) -> OrderCreate:
    return OrderCreate.model_validate(
        {
            "items": [
                {"product_id": str(product_id), "quantity": quantity}
                for product_id, quantity in items
            ]
        }
    )


def test_same_validated_request_has_same_fingerprint() -> None:
    payload = order_payload([(PRODUCT_A, 1), (PRODUCT_B, 2)])

    assert order_request_fingerprint(payload) == order_request_fingerprint(payload)


def test_item_order_does_not_change_fingerprint() -> None:
    first = order_payload([(PRODUCT_A, 1), (PRODUCT_B, 2)])
    reordered = order_payload([(PRODUCT_B, 2), (PRODUCT_A, 1)])

    assert order_request_fingerprint(first) == order_request_fingerprint(reordered)


def test_quantity_changes_fingerprint() -> None:
    first = order_payload([(PRODUCT_A, 1)])
    changed = order_payload([(PRODUCT_A, 2)])

    assert order_request_fingerprint(first) != order_request_fingerprint(changed)


def test_product_changes_fingerprint() -> None:
    first = order_payload([(PRODUCT_A, 1)])
    changed = order_payload([(PRODUCT_C, 1)])

    assert order_request_fingerprint(first) != order_request_fingerprint(changed)


def test_fingerprint_is_lowercase_sha256_hex() -> None:
    fingerprint = order_request_fingerprint(order_payload([(PRODUCT_A, 1)]))

    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
