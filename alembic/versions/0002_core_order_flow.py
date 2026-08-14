"""Create the Product, Order, and OrderItem domain schema.

Revision ID: 0002_core_order_flow
Revises: 0001_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_core_order_flow"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the complete M2 relational schema."""

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(sku)) > 0",
            name="ck_products_sku_not_blank",
        ),
        sa.CheckConstraint("sku = btrim(sku)", name="ck_products_sku_trimmed"),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0",
            name="ck_products_name_not_blank",
        ),
        sa.CheckConstraint("name = btrim(name)", name="ck_products_name_trimmed"),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_products_unit_price_nonnegative",
        ),
        sa.CheckConstraint(
            "stock_quantity >= 0",
            name="ck_products_stock_quantity_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'PENDING' AND confirmed_at IS NULL) OR "
            "(status = 'CONFIRMED' AND confirmed_at IS NOT NULL)",
            name="ck_orders_status_confirmed_at_coherent",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED')",
            name="ck_orders_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_order_items_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_order_items_unit_price_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_items_order_id_orders",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_order_items_product_id_products",
        ),
        sa.PrimaryKeyConstraint("order_id", "product_id", name="pk_order_items"),
    )


def downgrade() -> None:
    """Drop the M2 schema while preserving the M1 baseline."""

    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("products")
