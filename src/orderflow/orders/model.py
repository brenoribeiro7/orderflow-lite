"""SQLAlchemy models for orders and immutable item price snapshots."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orderflow.db.base import Base, utc_now


class OrderStatus(StrEnum):
    """The complete state set supported by OrderFlow Lite v1."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"


order_status_type = Enum(
    OrderStatus,
    name="order_status",
    native_enum=False,
    create_constraint=False,
    validate_strings=True,
    length=16,
)


class Order(Base):
    """A complete pending or confirmed order."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED')",
            name="ck_orders_status_valid",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND confirmed_at IS NULL) OR "
            "(status = 'CONFIRMED' AND confirmed_at IS NOT NULL)",
            name="ck_orders_status_confirmed_at_coherent",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    status: Mapped[OrderStatus] = mapped_column(
        order_status_type,
        default=OrderStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.product_id",
    )


class OrderItem(Base):
    """An order line with the product price captured at order creation."""

    __tablename__ = "order_items"
    __table_args__ = (
        PrimaryKeyConstraint("order_id", "product_id", name="pk_order_items"),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint(
            "unit_price >= 0",
            name="ck_order_items_unit_price_nonnegative",
        ),
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", name="fk_order_items_order_id_orders"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", name="fk_order_items_product_id_products"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")
