"""Allow replay-safe partial demand-notice fulfillment.

Revision ID: e18b6a904f31
Revises: d51f7a92c8e4
"""
from alembic import op
import sqlalchemy as sa

revision = "e18b6a904f31"
down_revision = "d51f7a92c8e4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sales_orders", schema=None) as batch_op:
        batch_op.drop_constraint("uq_sales_orders_source_demand_notice", type_="unique")
    op.create_table(
        "commercial_demand_notice_fulfillments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("notice_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("deposit_applied", sa.Numeric(precision=14, scale=3), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fulfilled_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_demand_notice_fulfillments_quantity_positive"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fulfilled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "notice_id"],
            ["commercial_demand_notices.tenant_container_id", "commercial_demand_notices.company_id", "commercial_demand_notices.id"],
            name="fk_demand_notice_fulfillments_notice", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "order_id"],
            ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"],
            name="fk_demand_notice_fulfillments_order", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "notice_id", "idempotency_key", name="uq_demand_notice_fulfillment_key"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_demand_notice_fulfillment_container_id"),
    )
    op.create_index(
        "ix_demand_notice_fulfillment_notice",
        "commercial_demand_notice_fulfillments",
        ["tenant_container_id", "company_id", "notice_id", "created_at"],
        unique=False,
    )


def downgrade():
    connection = op.get_bind()
    duplicates = connection.execute(sa.text(
        "SELECT count(*) FROM (SELECT company_id, source_demand_notice_id FROM sales_orders "
        "WHERE source_demand_notice_id IS NOT NULL GROUP BY company_id, source_demand_notice_id HAVING count(*) > 1) AS duplicate_sources"
    )).scalar_one()
    if duplicates:
        raise RuntimeError("Cannot restore one-order-per-notice constraint while partial fulfillment orders exist.")
    op.drop_index("ix_demand_notice_fulfillment_notice", table_name="commercial_demand_notice_fulfillments")
    op.drop_table("commercial_demand_notice_fulfillments")
    with op.batch_alter_table("sales_orders", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_sales_orders_source_demand_notice", ["company_id", "source_demand_notice_id"])
