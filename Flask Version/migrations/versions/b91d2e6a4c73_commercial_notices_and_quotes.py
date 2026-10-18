"""Add tenant-scoped demand notices, quotations, and conversion links.

Revision ID: b91d2e6a4c73
Revises: a7f5c1d39e84
Create Date: 2026-10-18
"""

from alembic import op
import sqlalchemy as sa

revision = "b91d2e6a4c73"
down_revision = "a7f5c1d39e84"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "business_number_series",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("document_type", sa.String(length=24), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("document_type IN ('demand_notice', 'quotation')", name="ck_business_number_series_type"),
        sa.CheckConstraint("next_number > 0", name="ck_business_number_series_next_positive"),
        sa.CheckConstraint("length(trim(prefix)) > 0", name="ck_business_number_series_prefix_nonempty"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_business_number_series_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_business_number_series_company_container", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "document_type", name="uq_business_number_series_company_type"),
        sa.UniqueConstraint("company_id", "prefix", name="uq_business_number_series_company_prefix"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_business_number_series_container_company", "business_number_series", ["tenant_container_id", "company_id"])

    op.create_table(
        "commercial_demand_notices",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=64), nullable=False),
        sa.Column("notice_number", sa.String(length=64), nullable=False),
        sa.Column("salesperson_id", sa.String(length=64), nullable=True),
        sa.Column("customer_name", sa.String(length=160), nullable=True),
        sa.Column("customer_phone", sa.String(length=64), nullable=False),
        sa.Column("phone_search", sa.String(length=32), nullable=False),
        sa.Column("product_owner_company_id", sa.String(length=64), nullable=True),
        sa.Column("product_id", sa.String(length=64), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_sku", sa.String(length=128), nullable=True),
        sa.Column("quantity_requested", sa.Integer(), nullable=False),
        sa.Column("quantity_fulfilled", sa.Integer(), nullable=False),
        sa.Column("agreed_price", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("expected_availability_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("is_new_product", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("updated_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open', 'converted', 'cancelled')", name="ck_commercial_demand_notices_status"),
        sa.CheckConstraint("quantity_requested > 0", name="ck_commercial_demand_notices_quantity_positive"),
        sa.CheckConstraint("quantity_fulfilled >= 0 AND quantity_fulfilled <= quantity_requested", name="ck_commercial_demand_notices_fulfilled_range"),
        sa.CheckConstraint("agreed_price IS NULL OR agreed_price >= 0", name="ck_commercial_demand_notices_price_nonnegative"),
        sa.CheckConstraint("(product_owner_company_id IS NULL AND product_id IS NULL) OR (product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)", name="ck_commercial_demand_notices_product_pair"),
        sa.CheckConstraint("is_new_product IN (0, 1)", name="ck_commercial_demand_notices_new_product_bool"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_commercial_demand_notices_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["salesperson_id"], ["users.id"], name="fk_commercial_demand_notices_salesperson_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_commercial_demand_notices_created_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_commercial_demand_notices_updated_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_commercial_demand_notices_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "store_id"], ["stores.tenant_container_id", "stores.company_id", "stores.id"], name="fk_commercial_demand_notices_store_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "product_owner_company_id", "product_id"], ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"], name="fk_commercial_demand_notices_catalog_product", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "notice_number", name="uq_commercial_demand_notices_company_number"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_commercial_demand_notices_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_commercial_demand_notices_store_status_date", "commercial_demand_notices", ["tenant_container_id", "company_id", "store_id", "status", "created_at"])
    op.create_index("ix_commercial_demand_notices_phone", "commercial_demand_notices", ["tenant_container_id", "company_id", "phone_search"])

    op.create_table(
        "commercial_quotations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=64), nullable=False),
        sa.Column("quotation_number", sa.String(length=64), nullable=False),
        sa.Column("salesperson_id", sa.String(length=64), nullable=True),
        sa.Column("customer_name", sa.String(length=160), nullable=True),
        sa.Column("customer_phone", sa.String(length=64), nullable=False),
        sa.Column("customer_email", sa.String(length=254), nullable=True),
        sa.Column("customer_address", sa.Text(), nullable=True),
        sa.Column("preparation_days", sa.Integer(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("updated_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'sent', 'accepted', 'rejected', 'cancelled', 'expired', 'converted')", name="ck_commercial_quotations_status"),
        sa.CheckConstraint("preparation_days >= 0", name="ck_commercial_quotations_preparation_nonnegative"),
        sa.CheckConstraint("total_amount >= 0", name="ck_commercial_quotations_total_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_commercial_quotations_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["salesperson_id"], ["users.id"], name="fk_commercial_quotations_salesperson_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_commercial_quotations_created_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_commercial_quotations_updated_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_commercial_quotations_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "store_id"], ["stores.tenant_container_id", "stores.company_id", "stores.id"], name="fk_commercial_quotations_store_container", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "quotation_number", name="uq_commercial_quotations_company_number"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_commercial_quotations_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_commercial_quotations_store_status_created", "commercial_quotations", ["tenant_container_id", "company_id", "store_id", "status", "created_at"])
    op.create_index("ix_commercial_quotations_phone", "commercial_quotations", ["tenant_container_id", "company_id", "customer_phone"])

    op.create_table(
        "commercial_quotation_lines",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("quotation_id", sa.String(length=64), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_owner_company_id", sa.String(length=64), nullable=True),
        sa.Column("product_id", sa.String(length=64), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_sku", sa.String(length=128), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("is_external", sa.Boolean(), nullable=False),
        sa.Column("converted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("line_number > 0", name="ck_commercial_quotation_lines_number_positive"),
        sa.CheckConstraint("quantity > 0", name="ck_commercial_quotation_lines_quantity_positive"),
        sa.CheckConstraint("unit_price > 0", name="ck_commercial_quotation_lines_price_positive"),
        sa.CheckConstraint("line_total > 0", name="ck_commercial_quotation_lines_total_positive"),
        sa.CheckConstraint("(is_external = 1 AND product_owner_company_id IS NULL AND product_id IS NULL) OR (is_external = 0 AND product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)", name="ck_commercial_quotation_lines_external_product_pair"),
        sa.CheckConstraint("is_external IN (0, 1)", name="ck_commercial_quotation_lines_external_bool"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_commercial_quotation_lines_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "quotation_id"], ["commercial_quotations.tenant_container_id", "commercial_quotations.company_id", "commercial_quotations.id"], name="fk_commercial_quotation_lines_quotation_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "product_owner_company_id", "product_id"], ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"], name="fk_commercial_quotation_lines_catalog_product", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "quotation_id", "line_number", name="uq_commercial_quotation_lines_quote_number"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_commercial_quotation_lines_quote", "commercial_quotation_lines", ["tenant_container_id", "company_id", "quotation_id"])

    with op.batch_alter_table("sales_orders") as batch:
        batch.add_column(sa.Column("source_demand_notice_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("source_quotation_id", sa.String(length=64), nullable=True))
        batch.create_check_constraint("ck_sales_orders_one_commercial_source", "source_demand_notice_id IS NULL OR source_quotation_id IS NULL")
        batch.create_unique_constraint("uq_sales_orders_source_demand_notice", ["company_id", "source_demand_notice_id"])
        batch.create_unique_constraint("uq_sales_orders_source_quotation", ["company_id", "source_quotation_id"])
        batch.create_foreign_key(
            "fk_sales_orders_source_demand_notice",
            "commercial_demand_notices",
            ["tenant_container_id", "company_id", "source_demand_notice_id"],
            ["tenant_container_id", "company_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_sales_orders_source_quotation",
            "commercial_quotations",
            ["tenant_container_id", "company_id", "source_quotation_id"],
            ["tenant_container_id", "company_id", "id"],
            ondelete="RESTRICT",
        )


def downgrade():
    bind = op.get_bind()
    for table in ("sales_orders", "commercial_quotation_lines", "commercial_quotations", "commercial_demand_notices", "business_number_series"):
        if table == "sales_orders":
            count = bind.execute(sa.text("SELECT COUNT(*) FROM sales_orders WHERE source_demand_notice_id IS NOT NULL OR source_quotation_id IS NOT NULL")).scalar_one()
        else:
            count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(f"Refusing to remove commercial workflow data from {table}.")

    with op.batch_alter_table("sales_orders") as batch:
        batch.drop_constraint("fk_sales_orders_source_demand_notice", type_="foreignkey")
        batch.drop_constraint("fk_sales_orders_source_quotation", type_="foreignkey")
        batch.drop_constraint("uq_sales_orders_source_demand_notice", type_="unique")
        batch.drop_constraint("uq_sales_orders_source_quotation", type_="unique")
        batch.drop_constraint("ck_sales_orders_one_commercial_source", type_="check")
        batch.drop_column("source_demand_notice_id")
        batch.drop_column("source_quotation_id")
    op.drop_index("ix_commercial_quotation_lines_quote", table_name="commercial_quotation_lines")
    op.drop_table("commercial_quotation_lines")
    op.drop_index("ix_commercial_quotations_phone", table_name="commercial_quotations")
    op.drop_index("ix_commercial_quotations_store_status_created", table_name="commercial_quotations")
    op.drop_table("commercial_quotations")
    op.drop_index("ix_commercial_demand_notices_phone", table_name="commercial_demand_notices")
    op.drop_index("ix_commercial_demand_notices_store_status_date", table_name="commercial_demand_notices")
    op.drop_table("commercial_demand_notices")
    op.drop_index("ix_business_number_series_container_company", table_name="business_number_series")
    op.drop_table("business_number_series")
