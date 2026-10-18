"""add audited order returns and tendered refunds

Revision ID: a7f5c1d39e84
Revises: f12c8e6a97d0
Create Date: 2026-10-18
"""

from alembic import op
import sqlalchemy as sa

revision = "a7f5c1d39e84"
down_revision = "f12c8e6a97d0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("daily_cashups") as batch:
        batch.drop_constraint("ck_daily_cashups_amounts_nonnegative", type_="check")
        batch.create_check_constraint(
            "ck_daily_cashups_counted_amounts_nonnegative",
            "counted_cash >= 0 AND counted_bank >= 0 AND counted_bank_transfer >= 0 AND counted_other >= 0",
        )

    op.create_table(
        "order_returns",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=64), nullable=False),
        sa.Column("refund_method", sa.String(length=24), nullable=False),
        sa.Column("refund_amount", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("transaction_reference", sa.String(length=128), nullable=True),
        sa.Column("processed_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("refund_method IN ('cash', 'bank', 'bank_transfer', 'other')", name="ck_order_returns_refund_method"),
        sa.CheckConstraint("refund_amount > 0", name="ck_order_returns_refund_amount_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_order_returns_tenant_container_id_tenant_containers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"],
            name="fk_order_returns_company_container", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "order_id"],
            ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"],
            name="fk_order_returns_order_container", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_order_returns_store_container", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["processed_by_id"], ["users.id"],
            name="fk_order_returns_processed_by_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_order_returns_company_idempotency"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_order_returns_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_order_returns_company_order_created",
        "order_returns",
        ["tenant_container_id", "company_id", "order_id", "created_at"],
    )
    op.create_index(
        "ix_order_returns_company_store_created",
        "order_returns",
        ["tenant_container_id", "company_id", "store_id", "created_at"],
    )

    op.create_table(
        "order_return_lines",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("return_id", sa.String(length=64), nullable=False),
        sa.Column("sales_order_line_id", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_return_lines_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_return_lines_unit_price_nonnegative"),
        sa.CheckConstraint("line_total >= 0", name="ck_order_return_lines_total_nonnegative"),
        sa.ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_order_return_lines_tenant_container_id_tenant_containers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "return_id"],
            ["order_returns.tenant_container_id", "order_returns.company_id", "order_returns.id"],
            name="fk_order_return_lines_return_container", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "sales_order_line_id"],
            ["sales_order_lines.tenant_container_id", "sales_order_lines.company_id", "sales_order_lines.id"],
            name="fk_order_return_lines_order_line_container", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_container_id", "company_id", "return_id", "sales_order_line_id",
            name="uq_order_return_lines_return_line",
        ),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_order_return_lines_container_line",
        "order_return_lines",
        ["tenant_container_id", "company_id", "sales_order_line_id"],
    )


def downgrade():
    bind = op.get_bind()
    return_count = bind.execute(sa.text("SELECT COUNT(*) FROM order_returns")).scalar_one()
    if return_count:
        raise RuntimeError("Refusing to drop financial return/refund history while records exist.")

    op.drop_index("ix_order_return_lines_container_line", table_name="order_return_lines")
    op.drop_table("order_return_lines")
    op.drop_index("ix_order_returns_company_store_created", table_name="order_returns")
    op.drop_index("ix_order_returns_company_order_created", table_name="order_returns")
    op.drop_table("order_returns")

    with op.batch_alter_table("daily_cashups") as batch:
        batch.drop_constraint("ck_daily_cashups_counted_amounts_nonnegative", type_="check")
        batch.create_check_constraint(
            "ck_daily_cashups_amounts_nonnegative",
            "expected_cash >= 0 AND expected_bank >= 0 AND expected_bank_transfer >= 0 AND expected_other >= 0 "
            "AND counted_cash >= 0 AND counted_bank >= 0 AND counted_bank_transfer >= 0 AND counted_other >= 0",
        )
