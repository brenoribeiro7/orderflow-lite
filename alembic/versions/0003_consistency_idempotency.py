"""Persist successful order-creation idempotency records.

Revision ID: 0003_consistency_idempotency
Revises: 0002_core_order_flow
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_consistency_idempotency"
down_revision: str | Sequence[str] | None = "0002_core_order_flow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the single M3 persistence structure."""

    op.create_table(
        "idempotency_records",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_idempotency_records_order_id_orders",
        ),
        sa.PrimaryKeyConstraint("key", name="pk_idempotency_records"),
        sa.UniqueConstraint(
            "order_id",
            name="uq_idempotency_records_order_id",
        ),
    )


def downgrade() -> None:
    """Remove only the M3 idempotency structure."""

    op.drop_table("idempotency_records")
