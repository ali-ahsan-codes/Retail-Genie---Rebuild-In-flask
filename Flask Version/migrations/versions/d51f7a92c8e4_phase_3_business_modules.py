"""Phase 3 business modules: settings, SCM, attendance, stock audits, messaging, cloud files, sales parity.

Revision ID: d51f7a92c8e4
Revises: b91d2e6a4c73
Create Date: 2026-10-19
"""

from alembic import op
import sqlalchemy as sa

revision = "d51f7a92c8e4"
down_revision = "b91d2e6a4c73"
branch_labels = None
depends_on = None


def upgrade():
    # ---- Settings ----
    op.create_table(
        "settings_tax",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("rate", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rate >= 0", name="ck_tax_settings_rate_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_tax_settings_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_tax_settings_company_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_tax_settings_created_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_tax_settings_container_company_id"),
        sa.UniqueConstraint("company_id", "name", name="uq_tax_settings_company_name"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_tax_settings_container_company", "settings_tax", ["tenant_container_id", "company_id"])

    op.create_table(
        "settings_commission",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("sales_target", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("commission_interval", sa.String(length=16), nullable=False),
        sa.Column("commission_percentage", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sales_target >= 0", name="ck_commission_settings_target_nonnegative"),
        sa.CheckConstraint("commission_percentage >= 0", name="ck_commission_settings_percentage_nonnegative"),
        sa.CheckConstraint("commission_interval IN ('daily', 'weekly', 'monthly')", name="ck_commission_settings_interval"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_commission_settings_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_commission_settings_company_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_commission_settings_created_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_commission_settings_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_commission_settings_container_company", "settings_commission", ["tenant_container_id", "company_id"])

    op.create_table(
        "settings_global_discount",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("percentage", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("percentage >= 0 AND percentage <= 100", name="ck_global_discount_settings_percentage_range"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_global_discount_settings_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_global_discount_settings_company_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_global_discount_settings_created_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_global_discount_settings_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_global_discount_settings_container_company", "settings_global_discount", ["tenant_container_id", "company_id"])

    op.create_table(
        "settings_attendance",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("mandatory_attendance_time", sa.String(length=8), nullable=True),
        sa.Column("is_mandatory_attendance_active", sa.Boolean(), nullable=False),
        sa.Column("max_concurrent_breaks", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_concurrent_breaks >= 1", name="ck_attendance_settings_breaks_positive"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_attendance_settings_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_attendance_settings_company_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_attendance_settings_created_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_attendance_settings_container_company_id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", name="uq_attendance_settings_company"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_attendance_settings_container_company", "settings_attendance", ["tenant_container_id", "company_id"])

    op.create_table(
        "product_categories",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_product_categories_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_product_categories_company_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_product_categories_created_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_product_categories_container_company_id"),
        sa.UniqueConstraint("company_id", "name", name="uq_product_categories_company_name"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_product_categories_container_company", "product_categories", ["tenant_container_id", "company_id"])

    # ---- SCM ----
    op.create_table(
        "scm_suppliers",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("lead_time", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("supplier_status", sa.String(length=16), nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("updated_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("supplier_status IN ('active', 'inactive')", name="ck_suppliers_status"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_suppliers_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_suppliers_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_suppliers_created_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_suppliers_updated_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_suppliers_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_suppliers_container_company_active", "scm_suppliers", ["tenant_container_id", "company_id", "supplier_status"])

    op.create_table(
        "scm_supplier_products",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("supplier_id", sa.String(length=64), nullable=False),
        sa.Column("product_owner_company_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("document_path", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("unit_price >= 0", name="ck_supplier_products_unit_price_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_supplier_products_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_supplier_products_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "supplier_id"], ["scm_suppliers.tenant_container_id", "scm_suppliers.company_id", "scm_suppliers.id"], name="fk_supplier_products_supplier", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "product_owner_company_id", "product_id"], ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"], name="fk_supplier_products_product", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_supplier_products_created_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_supplier_products_container_company_id"),
        sa.UniqueConstraint("company_id", "supplier_id", "product_owner_company_id", "product_id", name="uq_supplier_products_supplier_product"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_supplier_products_container_supplier", "scm_supplier_products", ["tenant_container_id", "supplier_id"])

    op.create_table(
        "scm_supplier_attachments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("supplier_id", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("uploaded_by_id", sa.String(length=64), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_supplier_attachments_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_supplier_attachments_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "supplier_id"], ["scm_suppliers.tenant_container_id", "scm_suppliers.company_id", "scm_suppliers.id"], name="fk_supplier_attachments_supplier", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], name="fk_supplier_attachments_uploaded_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_supplier_attachments_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_supplier_attachments_container_supplier", "scm_supplier_attachments", ["tenant_container_id", "supplier_id"])

    op.create_table(
        "scm_purchase_orders",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("po_number", sa.String(length=64), nullable=False),
        sa.Column("supplier_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("advance_paid", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("expected_delivery", sa.Date(), nullable=True),
        sa.Column("transportation_details", sa.Text(), nullable=True),
        sa.Column("invoice_path", sa.Text(), nullable=True),
        sa.Column("logistics_status", sa.String(length=120), nullable=True),
        sa.Column("received_store_id", sa.String(length=64), nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("updated_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'confirmed', 'partially_received', 'received', 'cancelled')", name="ck_purchase_orders_status"),
        sa.CheckConstraint("total_amount >= 0", name="ck_purchase_orders_total_nonnegative"),
        sa.CheckConstraint("advance_paid >= 0", name="ck_purchase_orders_advance_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_purchase_orders_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_purchase_orders_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "supplier_id"], ["scm_suppliers.tenant_container_id", "scm_suppliers.company_id", "scm_suppliers.id"], name="fk_purchase_orders_supplier", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_purchase_orders_created_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_purchase_orders_updated_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_purchase_orders_container_company_id"),
        sa.UniqueConstraint("company_id", "po_number", name="uq_purchase_orders_company_number"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_purchase_orders_company_status_created", "scm_purchase_orders", ["tenant_container_id", "company_id", "status", "created_at"])

    op.create_table(
        "scm_po_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("po_id", sa.String(length=64), nullable=False),
        sa.Column("product_owner_company_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("quantity_ordered", sa.Integer(), nullable=False),
        sa.Column("quantity_received", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_ordered > 0", name="ck_po_items_quantity_ordered_positive"),
        sa.CheckConstraint("quantity_received >= 0", name="ck_po_items_quantity_received_nonnegative"),
        sa.CheckConstraint("unit_price >= 0", name="ck_po_items_unit_price_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_po_items_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_po_items_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "po_id"], ["scm_purchase_orders.tenant_container_id", "scm_purchase_orders.company_id", "scm_purchase_orders.id"], name="fk_po_items_po_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "product_owner_company_id", "product_id"], ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"], name="fk_po_items_product", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_po_items_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_po_items_container_po", "scm_po_items", ["tenant_container_id", "po_id"])

    op.create_table(
        "scm_po_attachments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("po_id", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("attachment_type", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("uploaded_by_id", sa.String(length=64), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attachment_type IN ('invoice', 'shipping', 'other')", name="ck_po_attachments_type"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_po_attachments_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_po_attachments_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "po_id"], ["scm_purchase_orders.tenant_container_id", "scm_purchase_orders.company_id", "scm_purchase_orders.id"], name="fk_po_attachments_po_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], name="fk_po_attachments_uploaded_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_po_attachments_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_po_attachments_container_po", "scm_po_attachments", ["tenant_container_id", "po_id"])

    # ---- Attendance and breaks ----
    op.create_table(
        "hr_attendance_logs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("attendance_date", sa.String(length=10), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("selfie_data_uri", sa.Text(), nullable=True),
        sa.Column("selfie_image_path", sa.Text(), nullable=True),
        sa.Column("clock_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("method IN ('auto', 'manual', 'selfie')", name="ck_attendance_logs_method"),
        sa.CheckConstraint("clock_out_at IS NULL OR clock_out_at > timestamp", name="ck_attendance_logs_clockout_order"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_attendance_logs_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_attendance_logs_company_container", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_attendance_logs_container_company_id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "user_id", "attendance_date", name="uq_attendance_logs_company_user_day"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_attendance_logs_container_company_date", "hr_attendance_logs", ["tenant_container_id", "company_id", "attendance_date"])

    op.create_table(
        "hr_break_logs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_break_logs_duration_nonnegative"),
        sa.CheckConstraint("end_time IS NULL OR end_time >= start_time", name="ck_break_logs_end_order"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_break_logs_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_break_logs_company_container", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_break_logs_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_break_logs_container_user_start", "hr_break_logs", ["tenant_container_id", "user_id", "start_time"])

    # ---- Stock audits ----
    op.create_table(
        "stock_audits",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=64), nullable=False),
        sa.Column("audit_number", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("store_location", sa.String(length=160), nullable=True),
        sa.Column("admin_id", sa.String(length=64), nullable=True),
        sa.Column("auditor_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("auditor_selfie_path", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("updated_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'in_progress', 'completed', 'cancelled')", name="ck_stock_audits_status"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_stock_audits_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_stock_audits_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "store_id"], ["stores.tenant_container_id", "stores.company_id", "stores.id"], name="fk_stock_audits_store_scope", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], name="fk_stock_audits_admin_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["auditor_id"], ["users.id"], name="fk_stock_audits_auditor_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_stock_audits_created_by_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_stock_audits_updated_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stock_audits_container_company_id"),
        sa.UniqueConstraint("company_id", "audit_number", name="uq_stock_audits_company_number"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_stock_audits_company_store_status", "stock_audits", ["tenant_container_id", "company_id", "store_id", "status"])

    op.create_table(
        "stock_audit_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("audit_id", sa.String(length=64), nullable=False),
        sa.Column("product_owner_company_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_sku", sa.String(length=128), nullable=True),
        sa.Column("current_stock", sa.Integer(), nullable=False),
        sa.Column("final_audited_qty", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_stock >= 0", name="ck_stock_audit_items_current_stock_nonnegative"),
        sa.CheckConstraint("final_audited_qty IS NULL OR final_audited_qty >= 0", name="ck_stock_audit_items_final_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_stock_audit_items_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_stock_audit_items_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "audit_id"], ["stock_audits.tenant_container_id", "stock_audits.company_id", "stock_audits.id"], name="fk_stock_audit_items_audit_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "product_owner_company_id", "product_id"], ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"], name="fk_stock_audit_items_product", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stock_audit_items_container_company_id"),
        sa.UniqueConstraint("company_id", "audit_id", "product_id", name="uq_stock_audit_items_audit_product"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_stock_audit_items_container_audit", "stock_audit_items", ["tenant_container_id", "audit_id"])

    op.create_table(
        "stock_audit_item_counts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("audit_item_id", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("counted_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("count >= 0", name="ck_stock_audit_item_counts_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_stock_audit_item_counts_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_stock_audit_item_counts_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "audit_item_id"], ["stock_audit_items.tenant_container_id", "stock_audit_items.company_id", "stock_audit_items.id"], name="fk_stock_audit_item_counts_item_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["counted_by_id"], ["users.id"], name="fk_stock_audit_item_counts_counted_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stock_audit_item_counts_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_stock_audit_item_counts_container_item", "stock_audit_item_counts", ["tenant_container_id", "audit_item_id"])

    op.create_table(
        "stock_audit_images",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("count_event_id", sa.String(length=64), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_stock_audit_images_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_stock_audit_images_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "count_event_id"], ["stock_audit_item_counts.tenant_container_id", "stock_audit_item_counts.company_id", "stock_audit_item_counts.id"], name="fk_stock_audit_images_count_container", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stock_audit_images_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_stock_audit_images_container_count", "stock_audit_images", ["tenant_container_id", "count_event_id"])

    # ---- Messaging ----
    op.create_table(
        "messaging_conversations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=True),
        sa.Column("subject", sa.String(length=160), nullable=True),
        sa.Column("participant_ids", sa.JSON(), nullable=False),
        sa.Column("creator_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_conversations_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_conversations_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], name="fk_conversations_creator_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_conversations_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_conversations_container_created", "messaging_conversations", ["tenant_container_id", "created_at"])

    op.create_table(
        "messaging_messages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=True),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("sender_id", sa.String(length=64), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_messages_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_messages_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "conversation_id"], ["messaging_conversations.tenant_container_id", "messaging_conversations.company_id", "messaging_conversations.id"], name="fk_messages_conversation_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], name="fk_messages_sender_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_messages_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_messages_container_conversation_sent", "messaging_messages", ["tenant_container_id", "conversation_id", "sent_at"])

    op.create_table(
        "messaging_message_recipients",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=True),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("recipient_id", sa.String(length=64), nullable=False),
        sa.Column("recipient_type", sa.String(length=16), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("recipient_type IN ('user', 'role')", name="ck_message_recipients_type"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_message_recipients_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_message_recipients_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "message_id"], ["messaging_messages.tenant_container_id", "messaging_messages.company_id", "messaging_messages.id"], name="fk_message_recipients_message_container", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_message_recipients_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_message_recipients_container_recipient", "messaging_message_recipients", ["tenant_container_id", "recipient_id"])

    op.create_table(
        "messaging_attachments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=True),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_attachments_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_attachments_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "message_id"], ["messaging_messages.tenant_container_id", "messaging_messages.company_id", "messaging_messages.id"], name="fk_attachments_message_container", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_attachments_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_attachments_container_message", "messaging_attachments", ["tenant_container_id", "message_id"])

    # ---- Cloud files ----
    op.create_table(
        "cloud_files",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("owner_company_id", sa.String(length=64), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("share_scope", sa.String(length=16), nullable=False),
        sa.Column("share_unit_id", sa.String(length=64), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes >= 0", name="ck_cloud_files_size_nonnegative"),
        sa.CheckConstraint("share_scope IN ('container', 'company', 'store', 'user')", name="ck_cloud_files_share_scope"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_cloud_files_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "owner_company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_cloud_files_owner_company", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_cloud_files_owner_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "id", name="uq_cloud_files_container_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_cloud_files_container_owner", "cloud_files", ["tenant_container_id", "owner_user_id"])

    op.create_table(
        "cloud_file_shares",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=True),
        sa.Column("file_id", sa.String(length=64), nullable=False),
        sa.Column("shared_with_user_id", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_cloud_file_shares_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_cloud_file_shares_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "file_id"], ["cloud_files.tenant_container_id", "cloud_files.id"], name="fk_cloud_file_shares_file_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_with_user_id"], ["users.id"], name="fk_cloud_file_shares_shared_with_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_cloud_file_shares_created_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "file_id", "shared_with_user_id", name="uq_cloud_file_shares_file_user"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_cloud_file_shares_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_cloud_file_shares_container_recipient", "cloud_file_shares", ["tenant_container_id", "shared_with_user_id"])

    # ---- Store credit ----
    op.create_table(
        "store_credits",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("credit_number", sa.String(length=64), nullable=False),
        sa.Column("customer_name", sa.String(length=160), nullable=True),
        sa.Column("customer_phone", sa.String(length=64), nullable=False),
        sa.Column("phone_search", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("remaining_amount", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_order_id", sa.String(length=64), nullable=True),
        sa.Column("source_return_id", sa.String(length=64), nullable=True),
        sa.Column("issued_by_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_store_credits_amount_positive"),
        sa.CheckConstraint("remaining_amount >= 0", name="ck_store_credits_remaining_nonnegative"),
        sa.CheckConstraint("remaining_amount <= amount", name="ck_store_credits_remaining_range"),
        sa.CheckConstraint("status IN ('open', 'fully_used', 'expired', 'voided')", name="ck_store_credits_status"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_store_credits_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_store_credits_company_container", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "source_order_id"], ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"], name="fk_store_credits_source_order", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "source_return_id"], ["order_returns.tenant_container_id", "order_returns.company_id", "order_returns.id"], name="fk_store_credits_source_return", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["issued_by_id"], ["users.id"], name="fk_store_credits_issued_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "credit_number", name="uq_store_credits_company_number"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_store_credits_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_store_credits_company_phone", "store_credits", ["tenant_container_id", "company_id", "phone_search"])

    with op.batch_alter_table("order_payments", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_order_payments_container_company_id", ["tenant_container_id", "company_id", "id"])

    op.create_table(
        "store_credit_redemptions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("store_credit_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("payment_id", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("processed_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_store_credit_redemptions_amount_positive"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_store_credit_redemptions_tenant_container_id_tenant_containers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "store_credit_id"], ["store_credits.tenant_container_id", "store_credits.company_id", "store_credits.id"], name="fk_store_credit_redemptions_credit", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "order_id"], ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"], name="fk_store_credit_redemptions_order", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id", "payment_id"], ["order_payments.tenant_container_id", "order_payments.company_id", "order_payments.id"], name="fk_store_credit_redemptions_payment", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["processed_by_id"], ["users.id"], name="fk_store_credit_redemptions_processed_by_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_store_credit_redemptions_company_idempotency"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_store_credit_redemptions_container_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_store_credit_redemptions_container_credit", "store_credit_redemptions", ["tenant_container_id", "store_credit_id"])

    # ---- Sales order parity columns ----
    with op.batch_alter_table("sales_orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_return_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("checkout_idempotency_key", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("checkout_request_hash", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint("uq_sales_orders_company_checkout_idempotency", ["company_id", "checkout_idempotency_key"])
        batch_op.add_column(sa.Column("subtotal_amount", sa.Numeric(precision=14, scale=3), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("discount_amount", sa.Numeric(precision=14, scale=3), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("applied_discount_percentage", sa.Numeric(precision=12, scale=8), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("applied_global_discount_percentage", sa.Numeric(precision=12, scale=8), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("taxes", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("delivery_status", sa.String(length=24), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("delivery_address", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("storekeeper_notes", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("cashier_notes", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("reminder_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("reminder_notes", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("primary_salesperson_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("secondary_salesperson_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key("fk_sales_orders_primary_salesperson", "users", ["primary_salesperson_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_sales_orders_secondary_salesperson", "users", ["secondary_salesperson_id"], ["id"], ondelete="SET NULL")
        batch_op.add_column(sa.Column("primary_commission_rate", sa.Numeric(precision=12, scale=8), nullable=True))
        batch_op.add_column(sa.Column("secondary_commission_rate", sa.Numeric(precision=12, scale=8), nullable=True))
        batch_op.create_check_constraint("ck_sales_orders_delivery_status", "delivery_status IN ('pending', 'partially_delivered', 'delivered', 'cancelled')")
        batch_op.create_check_constraint("ck_sales_orders_subtotal_nonnegative", "subtotal_amount >= 0")
        batch_op.create_check_constraint("ck_sales_orders_discount_nonnegative", "discount_amount >= 0")
        batch_op.create_check_constraint("ck_sales_orders_discount_pct_range", "applied_discount_percentage >= 0 AND applied_discount_percentage <= 100")
        batch_op.create_check_constraint("ck_sales_orders_global_discount_pct_range", "applied_global_discount_percentage >= 0 AND applied_global_discount_percentage <= 100")

    with op.batch_alter_table("order_returns", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", sa.String(length=16), nullable=False, server_default="refund"))
        batch_op.add_column(sa.Column("exchange_order_id", sa.String(length=64), nullable=True))
        batch_op.create_check_constraint("ck_order_returns_kind", "kind IN ('refund', 'exchange', 'store_credit')")

    with op.batch_alter_table("commercial_demand_notices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("salesperson_name", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("payments", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("amount_paid", sa.Numeric(precision=14, scale=3), nullable=False, server_default="0"))

    with op.batch_alter_table("business_number_series", schema=None) as batch_op:
        batch_op.drop_constraint("ck_business_number_series_type", type_="check")
        batch_op.create_check_constraint(
            "ck_business_number_series_type",
            "document_type IN ('demand_notice', 'quotation', 'purchase_order', 'store_credit')",
        )


def downgrade():
    with op.batch_alter_table("business_number_series", schema=None) as batch_op:
        batch_op.drop_constraint("ck_business_number_series_type", type_="check")
        batch_op.create_check_constraint("ck_business_number_series_type", "document_type IN ('demand_notice', 'quotation')")

    with op.batch_alter_table("commercial_demand_notices", schema=None) as batch_op:
        batch_op.drop_column("amount_paid")
        batch_op.drop_column("payments")
        batch_op.drop_column("salesperson_name")

    with op.batch_alter_table("order_returns", schema=None) as batch_op:
        batch_op.drop_constraint("ck_order_returns_kind", type_="check")
        batch_op.drop_column("exchange_order_id")
        batch_op.drop_column("kind")

    with op.batch_alter_table("sales_orders", schema=None) as batch_op:
        batch_op.drop_constraint("uq_sales_orders_company_checkout_idempotency", type_="unique")
        batch_op.drop_constraint("ck_sales_orders_global_discount_pct_range", type_="check")
        batch_op.drop_constraint("ck_sales_orders_discount_pct_range", type_="check")
        batch_op.drop_constraint("ck_sales_orders_discount_nonnegative", type_="check")
        batch_op.drop_constraint("ck_sales_orders_subtotal_nonnegative", type_="check")
        batch_op.drop_constraint("ck_sales_orders_delivery_status", type_="check")
        batch_op.drop_constraint("fk_sales_orders_secondary_salesperson", type_="foreignkey")
        batch_op.drop_constraint("fk_sales_orders_primary_salesperson", type_="foreignkey")
        batch_op.drop_column("secondary_commission_rate")
        batch_op.drop_column("primary_commission_rate")
        batch_op.drop_column("secondary_salesperson_id")
        batch_op.drop_column("primary_salesperson_id")
        batch_op.drop_column("reminder_notes")
        batch_op.drop_column("reminder_date")
        batch_op.drop_column("cashier_notes")
        batch_op.drop_column("storekeeper_notes")
        batch_op.drop_column("delivery_address")
        batch_op.drop_column("delivery_status")
        batch_op.drop_column("taxes")
        batch_op.drop_column("applied_global_discount_percentage")
        batch_op.drop_column("applied_discount_percentage")
        batch_op.drop_column("discount_amount")
        batch_op.drop_column("subtotal_amount")
        batch_op.drop_column("checkout_request_hash")
        batch_op.drop_column("checkout_idempotency_key")
        batch_op.drop_column("source_return_id")

    op.drop_index("ix_store_credit_redemptions_container_credit", table_name="store_credit_redemptions")
    op.drop_table("store_credit_redemptions")
    with op.batch_alter_table("order_payments", schema=None) as batch_op:
        batch_op.drop_constraint("uq_order_payments_container_company_id", type_="unique")
    op.drop_index("ix_store_credits_company_phone", table_name="store_credits")
    op.drop_table("store_credits")
    op.drop_index("ix_cloud_file_shares_container_recipient", table_name="cloud_file_shares")
    op.drop_table("cloud_file_shares")
    op.drop_index("ix_cloud_files_container_owner", table_name="cloud_files")
    op.drop_table("cloud_files")
    op.drop_index("ix_attachments_container_message", table_name="messaging_attachments")
    op.drop_table("messaging_attachments")
    op.drop_index("ix_message_recipients_container_recipient", table_name="messaging_message_recipients")
    op.drop_table("messaging_message_recipients")
    op.drop_index("ix_messages_container_conversation_sent", table_name="messaging_messages")
    op.drop_table("messaging_messages")
    op.drop_index("ix_conversations_container_created", table_name="messaging_conversations")
    op.drop_table("messaging_conversations")
    op.drop_index("ix_stock_audit_images_container_count", table_name="stock_audit_images")
    op.drop_table("stock_audit_images")
    op.drop_index("ix_stock_audit_item_counts_container_item", table_name="stock_audit_item_counts")
    op.drop_table("stock_audit_item_counts")
    op.drop_index("ix_stock_audit_items_container_audit", table_name="stock_audit_items")
    op.drop_table("stock_audit_items")
    op.drop_index("ix_stock_audits_company_store_status", table_name="stock_audits")
    op.drop_table("stock_audits")
    op.drop_index("ix_break_logs_container_user_start", table_name="hr_break_logs")
    op.drop_table("hr_break_logs")
    op.drop_index("ix_attendance_logs_container_company_date", table_name="hr_attendance_logs")
    op.drop_table("hr_attendance_logs")
    op.drop_index("ix_po_attachments_container_po", table_name="scm_po_attachments")
    op.drop_table("scm_po_attachments")
    op.drop_index("ix_po_items_container_po", table_name="scm_po_items")
    op.drop_table("scm_po_items")
    op.drop_index("ix_purchase_orders_company_status_created", table_name="scm_purchase_orders")
    op.drop_table("scm_purchase_orders")
    op.drop_index("ix_supplier_attachments_container_supplier", table_name="scm_supplier_attachments")
    op.drop_table("scm_supplier_attachments")
    op.drop_index("ix_supplier_products_container_supplier", table_name="scm_supplier_products")
    op.drop_table("scm_supplier_products")
    op.drop_index("ix_suppliers_container_company_active", table_name="scm_suppliers")
    op.drop_table("scm_suppliers")
    op.drop_index("ix_product_categories_container_company", table_name="product_categories")
    op.drop_table("product_categories")
    op.drop_index("ix_attendance_settings_container_company", table_name="settings_attendance")
    op.drop_table("settings_attendance")
    op.drop_index("ix_global_discount_settings_container_company", table_name="settings_global_discount")
    op.drop_table("settings_global_discount")
    op.drop_index("ix_commission_settings_container_company", table_name="settings_commission")
    op.drop_table("settings_commission")
    op.drop_index("ix_tax_settings_container_company", table_name="settings_tax")
    op.drop_table("settings_tax")
