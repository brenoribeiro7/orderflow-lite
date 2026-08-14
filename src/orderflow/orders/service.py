"""Order use cases with explicit sequential transaction boundaries."""

import logging
from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from orderflow.api.error_handlers import ApiError
from orderflow.db.base import utc_now
from orderflow.orders.model import Order, OrderItem, OrderStatus
from orderflow.orders.schemas import OrderCreate
from orderflow.products.model import Product

logger = logging.getLogger(__name__)


def create_order(session: Session, payload: OrderCreate) -> Order:
    """Atomically persist a pending order and all price snapshots."""

    product_ids = [item.product_id for item in payload.items]

    try:
        with session.begin():
            products = session.scalars(
                select(Product).where(Product.id.in_(product_ids))
            ).all()
            products_by_id = {product.id: product for product in products}

            if any(product_id not in products_by_id for product_id in product_ids):
                raise ApiError(
                    status_code=404,
                    code="PRODUCT_NOT_FOUND",
                    message="One or more products were not found.",
                )

            order = Order(status=OrderStatus.PENDING)
            order.items = [
                OrderItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=products_by_id[item.product_id].unit_price,
                )
                for item in payload.items
            ]
            session.add(order)
    except IntegrityError:
        _raise_unexpected_integrity_error("creating an order")

    return order


def get_order(session: Session, order_id: UUID) -> Order:
    """Load one complete order with its items in a bounded query count."""

    order = session.scalar(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    if order is None:
        raise ApiError(
            status_code=404,
            code="ORDER_NOT_FOUND",
            message="Order was not found.",
        )
    return order


def confirm_order(session: Session, order_id: UUID) -> Order:
    """Confirm sequentially; M3 adds pessimistic locks for concurrent safety."""

    try:
        with session.begin():
            order = session.scalar(
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.id == order_id)
            )
            if order is None:
                raise ApiError(
                    status_code=404,
                    code="ORDER_NOT_FOUND",
                    message="Order was not found.",
                )
            if order.status == OrderStatus.CONFIRMED:
                raise ApiError(
                    status_code=409,
                    code="ORDER_ALREADY_CONFIRMED",
                    message="Order is already confirmed.",
                )

            product_ids = [item.product_id for item in order.items]
            products = session.scalars(
                select(Product).where(Product.id.in_(product_ids))
            ).all()
            products_by_id = {product.id: product for product in products}

            if len(products_by_id) != len(product_ids):
                logger.error("Order references a product that no longer exists")
                raise ApiError(
                    status_code=500,
                    code="INTERNAL_ERROR",
                    message="An internal error occurred.",
                )

            # Validate every line before mutating any stock to prevent partial debit.
            if any(
                products_by_id[item.product_id].stock_quantity < item.quantity
                for item in order.items
            ):
                raise ApiError(
                    status_code=409,
                    code="INSUFFICIENT_STOCK",
                    message="One or more products have insufficient stock.",
                )

            for item in order.items:
                products_by_id[item.product_id].stock_quantity -= item.quantity

            confirmed_at = utc_now()
            order.status = OrderStatus.CONFIRMED
            order.confirmed_at = confirmed_at
            order.updated_at = confirmed_at
    except IntegrityError:
        _raise_unexpected_integrity_error("confirming an order")

    return order


def _raise_unexpected_integrity_error(operation: str) -> NoReturn:
    logger.error("Unexpected integrity failure while %s", operation)
    raise ApiError(
        status_code=500,
        code="INTERNAL_ERROR",
        message="An internal error occurred.",
    ) from None
