"""add stable order references and catalog-linked sales stock movements

Revision ID: f12c8e6a97d0
Revises: d7a4c261f9e3
Create Date: 2026-10-18
"""

from alembic import op
import sqlalchemy as sa

revision = "f12c8e6a97d0"
down_revision = "d7a4c261f9e3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "order_number_series",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("next_number > 0", name="ck_order_number_series_positive_next"),
        sa.CheckConstraint("length(trim(prefix)) > 0", name="ck_order_number_series_nonempty_prefix"),
        sa.ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_order_number_series_tenant_container_id_tenant_containers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_order_number_series_company_container", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_order_number_series_company"),
        sa.UniqueConstraint("company_id", "prefix", name="uq_order_number_series_company_prefix"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_order_number_series_container_company",
        "order_number_series",
        ["tenant_container_id", "company_id"],
        unique=False,
    )

    op.add_column("sales_orders", sa.Column("order_number", sa.String(length=64), nullable=True))
    # Preserve existing primary keys as immutable references for any already-created
    # normalized orders. New orders receive a human-readable series number.
    op.execute("UPDATE sales_orders SET order_number = id WHERE order_number IS NULL")
    with op.batch_alter_table("sales_orders") as batch:
        batch.alter_column("order_number", existing_type=sa.String(length=64), nullable=False)
        batch.create_unique_constraint(
            "uq_sales_orders_company_order_number", ["company_id", "order_number"]
        )

    op.add_column("sales_order_lines", sa.Column("product_owner_company_id", sa.String(length=64), nullable=True))
    op.add_column("sales_order_lines", sa.Column("product_id", sa.String(length=64), nullable=True))
    with op.batch_alter_table("sales_order_lines") as batch:
        batch.create_check_constraint(
            "ck_sales_order_lines_product_link_pair",
            "(product_owner_company_id IS NULL AND product_id IS NULL) OR "
            "(product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)",
        )
        batch.create_foreign_key(
            "fk_sales_order_lines_catalog_product",
            "catalog_products",
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["tenant_container_id", "company_id", "id"],
            ondelete="RESTRICT",
        )

    dialect = op.get_context().dialect.name
    if dialect == "mysql":
        id_expression = "UUID()"
        utc_now_expression = "UTC_TIMESTAMP()"
    elif dialect == "sqlite":
        id_expression = "lower(hex(randomblob(16)))"
        utc_now_expression = "CURRENT_TIMESTAMP"
    else:
        raise RuntimeError(f"Unsupported order-number seed dialect: {dialect}")
    op.execute(
        "INSERT INTO order_number_series "
        "(id, tenant_container_id, company_id, prefix, next_number, is_active, created_at, updated_at) "
        f"SELECT {id_expression}, tenant_container_id, id, 'ORD-', 1, 1, "
        f"{utc_now_expression}, {utc_now_expression} FROM companies"
    )


def downgrade():
    bind = op.get_bind()
    order_count = bind.execute(sa.text("SELECT COUNT(*) FROM sales_orders")).scalar_one()
    if order_count:
        raise RuntimeError("Refusing to drop stable order references while sales orders exist.")
    with op.batch_alter_table("sales_order_lines") as batch:
        batch.drop_constraint("fk_sales_order_lines_catalog_product", type_="foreignkey")
        batch.drop_constraint("ck_sales_order_lines_product_link_pair", type_="check")
        batch.drop_column("product_id")
        batch.drop_column("product_owner_company_id")
    with op.batch_alter_table("sales_orders") as batch:
        batch.drop_constraint("uq_sales_orders_company_order_number", type_="unique")
        batch.drop_column("order_number")
    op.drop_index("ix_order_number_series_container_company", table_name="order_number_series")
    op.drop_table("order_number_series")
