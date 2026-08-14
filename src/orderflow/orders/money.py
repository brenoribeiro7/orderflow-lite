"""Pure derived money calculations for orders."""

from collections.abc import Iterable
from decimal import Decimal


def line_total(unit_price: Decimal, quantity: int) -> Decimal:
    """Calculate one order line without converting through float."""

    return unit_price * quantity


def total_amount(lines: Iterable[tuple[Decimal, int]]) -> Decimal:
    """Calculate an order total from non-persisted line totals."""

    return sum(
        (line_total(unit_price, quantity) for unit_price, quantity in lines),
        start=Decimal("0.00"),
    )
