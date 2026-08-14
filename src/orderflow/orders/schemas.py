"""Pydantic contracts and derived representations for orders."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orderflow.orders.model import Order, OrderStatus
from orderflow.orders.money import line_total, total_amount


class OrderItemCreate(BaseModel):
    """A requested product and quantity; prices always come from Product."""

    product_id: UUID
    quantity: Annotated[int, Field(gt=0)]


class OrderCreate(BaseModel):
    """Input for atomic creation of a complete pending order."""

    items: Annotated[list[OrderItemCreate], Field(min_length=1)]

    @model_validator(mode="after")
    def product_ids_must_be_unique(self) -> Self:
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Each product may appear only once in an order.")
        return self


class OrderItemResponse(BaseModel):
    """An order line with snapshot and derived monetary values."""

    product_id: UUID
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderResponse(BaseModel):
    """Public order representation with totals derived from item snapshots."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: OrderStatus
    items: list[OrderItemResponse]
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None

    @classmethod
    def from_order(cls, order: Order) -> Self:
        """Build response-only totals without persisting redundant money columns."""

        items = [
            OrderItemResponse(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=line_total(item.unit_price, item.quantity),
            )
            for item in sorted(order.items, key=lambda item: item.product_id)
        ]
        return cls(
            id=order.id,
            status=order.status,
            items=items,
            total_amount=total_amount(
                (item.unit_price, item.quantity) for item in order.items
            ),
            created_at=order.created_at,
            updated_at=order.updated_at,
            confirmed_at=order.confirmed_at,
        )
