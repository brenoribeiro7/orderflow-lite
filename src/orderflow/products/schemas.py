"""Pydantic contracts for product endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=18, decimal_places=2),
]
Sku = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]
ProductName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class ProductCreate(BaseModel):
    """Input accepted when creating a product."""

    sku: Sku
    name: ProductName
    unit_price: Money
    stock_quantity: Annotated[int, Field(ge=0)]


class ProductResponse(BaseModel):
    """Public product representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    unit_price: Decimal
    stock_quantity: int
    created_at: datetime
    updated_at: datetime
