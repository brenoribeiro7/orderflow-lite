"""Product use cases and their transaction boundaries."""

import logging
from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orderflow.api.error_handlers import ApiError
from orderflow.products.model import Product
from orderflow.products.schemas import ProductCreate

logger = logging.getLogger(__name__)


def create_product(session: Session, payload: ProductCreate) -> Product:
    """Persist one product in a transaction owned by this use case."""

    product = Product(
        sku=payload.sku,
        name=payload.name,
        unit_price=payload.unit_price,
        stock_quantity=payload.stock_quantity,
    )

    try:
        with session.begin():
            session.add(product)
    except IntegrityError as exc:
        if _is_duplicate_sku(exc):
            raise ApiError(
                status_code=409,
                code="SKU_ALREADY_EXISTS",
                message="A product with this SKU already exists.",
            ) from None

        logger.error("Unexpected integrity failure while creating a product")
        raise ApiError(
            status_code=500,
            code="INTERNAL_ERROR",
            message="An internal error occurred.",
        ) from None

    return product


def get_product(session: Session, product_id: UUID) -> Product:
    """Return a product or the stable not-found error."""

    product = session.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise ApiError(
            status_code=404,
            code="PRODUCT_NOT_FOUND",
            message="Product was not found.",
        )
    return product


def _is_duplicate_sku(exc: IntegrityError) -> bool:
    original = exc.orig
    return (
        isinstance(original, UniqueViolation)
        and original.diag.constraint_name == "uq_products_sku"
    )
