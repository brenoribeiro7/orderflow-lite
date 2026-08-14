"""Persistent reference for successful idempotent order creation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from orderflow.db.base import Base, utc_now


class IdempotencyRecord(Base):
    """Bind one opaque key and request fingerprint to one created Order."""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        PrimaryKeyConstraint("key", name="pk_idempotency_records"),
        UniqueConstraint("order_id", name="uq_idempotency_records_order_id"),
    )

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "orders.id",
            name="fk_idempotency_records_order_id_orders",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
