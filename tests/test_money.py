"""Pure money calculations and validation."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from orderflow.orders.money import line_total, total_amount
from orderflow.products.schemas import ProductCreate


def test_line_total_preserves_decimal_scale() -> None:
    assert line_total(Decimal("10.00"), 2) == Decimal("20.00")
    assert line_total(Decimal("19.99"), 3) == Decimal("59.97")
    assert isinstance(line_total(Decimal("1.25"), 2), Decimal)


def test_total_amount_sums_multiple_lines_as_decimal() -> None:
    result = total_amount([(Decimal("10.00"), 2), (Decimal("19.99"), 3)])

    assert result == Decimal("79.97")
    assert isinstance(result, Decimal)


@pytest.mark.parametrize("unit_price", ["10.99", "0"])
def test_valid_product_money_input(unit_price: str) -> None:
    product = ProductCreate(
        sku="SKU",
        name="Product",
        unit_price=unit_price,
        stock_quantity=0,
    )

    assert isinstance(product.unit_price, Decimal)


@pytest.mark.parametrize("unit_price", ["-0.01", "10.999"])
def test_invalid_product_money_input(unit_price: str) -> None:
    with pytest.raises(ValidationError):
        ProductCreate(
            sku="SKU",
            name="Product",
            unit_price=unit_price,
            stock_quantity=0,
        )
