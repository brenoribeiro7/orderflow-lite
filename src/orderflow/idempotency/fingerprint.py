"""Canonical request fingerprints for order-creation idempotency."""

import hashlib
import json

from orderflow.orders.schemas import OrderCreate


def order_request_fingerprint(payload: OrderCreate) -> str:
    """Hash only the client's validated order intent in a stable representation."""

    canonical_items = sorted(
        (
            {
                "product_id": str(item.product_id),
                "quantity": item.quantity,
            }
            for item in payload.items
        ),
        key=lambda item: str(item["product_id"]),
    )
    canonical_payload = {"items": canonical_items}
    serialized = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
