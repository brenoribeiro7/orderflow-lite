"""Order use cases with explicit transaction and concurrency boundaries."""

import logging
from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from orderflow.api.error_handlers import ApiError
from orderflow.db.base import utc_now
from orderflow.idempotency.fingerprint import order_request_fingerprint
from orderflow.idempotency.model import IdempotencyRecord
from orderflow.orders.model import Order, OrderItem, OrderStatus
from orderflow.orders.schemas import OrderCreate
from orderflow.products.model import Product

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderCreationResult:
    """Separate persistence outcome from the router's HTTP status decision."""

    order: Order
    replayed: bool


def create_order(
    session: Session,
    payload: OrderCreate,
    idempotency_key: str,
) -> OrderCreationResult:
    """Atomically create or replay an order using database key arbitration."""

    request_hash = order_request_fingerprint(payload)
    product_ids = [item.product_id for item in payload.items]

    try:
        with session.begin():
            existing_record = _find_idempotency_record(session, idempotency_key)
            if existing_record is not None:
                return _resolve_idempotency_record(
                    session,
                    existing_record,
                    request_hash,
                )

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
            session.flush()
            session.add(
                IdempotencyRecord(
                    key=idempotency_key,
                    request_hash=request_hash,
                    order_id=order.id,
                )
            )
    except IntegrityError as exc:
        if _is_idempotency_key_violation(exc):
            # The failed transaction is fully rolled back by session.begin() before
            # this new transaction reads the record committed by the winner.
            return _resolve_idempotency_race(
                session,
                idempotency_key,
                request_hash,
            )
        _raise_unexpected_integrity_error("creating an order")

    return OrderCreationResult(order=order, replayed=False)


def _find_idempotency_record(
    session: Session,
    idempotency_key: str,
) -> IdempotencyRecord | None:
    return session.get(IdempotencyRecord, idempotency_key)


def _resolve_idempotency_record(
    session: Session,
    record: IdempotencyRecord,
    request_hash: str,
) -> OrderCreationResult:
    if record.request_hash != request_hash:
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="Idempotency-Key was already used with a different request.",
        )

    order = session.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == record.order_id)
    )
    if order is None:
        logger.error("Idempotency record references an order that does not exist")
        raise ApiError(
            status_code=500,
            code="INTERNAL_ERROR",
            message="An internal error occurred.",
        )
    return OrderCreationResult(order=order, replayed=True)


def _resolve_idempotency_race(
    session: Session,
    idempotency_key: str,
    request_hash: str,
) -> OrderCreationResult:
    try:
        with session.begin():
            record = _find_idempotency_record(session, idempotency_key)
            if record is None:
                logger.error("Idempotency key arbitration completed without a winner")
                raise ApiError(
                    status_code=500,
                    code="INTERNAL_ERROR",
                    message="An internal error occurred.",
                )
            return _resolve_idempotency_record(session, record, request_hash)
    except IntegrityError:
        _raise_unexpected_integrity_error("resolving idempotency key arbitration")


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
    """Confirm with one deterministic pessimistic lock policy."""

    try:
        with session.begin():
            order = session.scalar(
                select(Order).where(Order.id == order_id).with_for_update()
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

            # OrderItem is immutable in v1.0 and is loaded only after the Order lock.
            items = list(order.items)
            product_ids = sorted(item.product_id for item in items)
            products = session.scalars(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id.asc())
                .with_for_update()
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
                for item in items
            ):
                raise ApiError(
                    status_code=409,
                    code="INSUFFICIENT_STOCK",
                    message="One or more products have insufficient stock.",
                )

            for item in items:
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


def _is_idempotency_key_violation(exc: IntegrityError) -> bool:
    original = exc.orig
    return (
        isinstance(original, UniqueViolation)
        and original.diag.constraint_name == "pk_idempotency_records"
    )
