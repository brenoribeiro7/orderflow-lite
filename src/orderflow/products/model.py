"""SQLAlchemy model for available products and stock."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from orderflow.db.base import Base, utc_now


class Product(Base):
    """A sellable product and its currently available stock."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_products_sku"),
        CheckConstraint("sku = btrim(sku)", name="ck_products_sku_trimmed"),
        CheckConstraint(
            "char_length(btrim(sku)) > 0",
            name="ck_products_sku_not_blank",
        ),
        CheckConstraint("name = btrim(name)", name="ck_products_name_trimmed"),
        CheckConstraint(
            "char_length(btrim(name)) > 0",
            name="ck_products_name_not_blank",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="ck_products_unit_price_nonnegative",
        ),
        CheckConstraint(
            "stock_quantity >= 0",
            name="ck_products_stock_quantity_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
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
