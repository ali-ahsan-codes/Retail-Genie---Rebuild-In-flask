"""Replace company-as-tenant with a logical tenant-container boundary.

Revision ID: ba2fd4c7e8a1
Revises: 93c522098bed
Create Date: 2026-10-18

Every pre-container company is migrated into its own tenant container, preserving
the prior company-as-tenant isolation. Business rows, staff assignments, and audit
events inherit that container. Restrictive company-level data-sharing policies are
seeded without granting cross-company sharing.
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "ba2fd4c7e8a1"
down_revision = "93c522098bed"
branch_labels = None
depends_on = None

LEGACY_TABLES = (
    "attachments",
    "attendance_logs",
    "attendance_settings",
    "audit_images",
    "audit_item_counts",
    "audit_items",
    "audits",
    "break_logs",
    "commission_settings",
    "conversations",
    "demand_notices",
    "global_discount_settings",
    "invoice_number_settings",
    "message_recipients",
    "messages",
    "orders",
    "po_attachments",
    "po_items",
    "products",
    "purchase_orders",
    "quotation_items",
    "quotations",
    "supplier_attachments",
    "supplier_products",
    "suppliers",
    "tax_settings",
)
DATA_DOMAINS = (
    "product_catalog",
    "inventory",
    "customers",
    "open_bills",
    "sales",
    "staff_accounts",
    "suppliers",
    "reports",
    "files",
    "audit",
    "cashups",
    "settings",
)
VALID_ROLES = "'super_admin', 'company_admin', 'admin', 'manager', 'salesperson', 'storekeeper', 'cashier', 'logistics', 'auditor', 'display', 'express'"


def _add_tenant_column(table_name: str) -> None:
    """Add/backfill the container id from the row's owning company."""
    op.add_column(table_name, sa.Column("tenant_container_id", sa.String(64), nullable=True))
    op.execute(
        sa.text(
            f"UPDATE {table_name} SET tenant_container_id = "
            f"(SELECT tenant_container_id FROM companies WHERE companies.id = {table_name}.company_id) "
            "WHERE tenant_container_id IS NULL"
        )
    )


def upgrade():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    op.create_table(
        "tenant_containers",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenant_containers_slug"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    # Each company in the prior schema represented an independent tenant. Reuse
    # its stable primary key, display name and globally-unique slug as the
    # container identity so this migration cannot silently merge customers.
    op.execute(
        sa.text(
            "INSERT INTO tenant_containers "
            "(id, name, slug, timezone, is_active, policy_version, created_at, updated_at) "
            "SELECT id, name, slug, timezone, is_active, 1, created_at, updated_at FROM companies"
        )
    )

    # Make tenant ownership canonical on companies and support only same-container
    # parent/child links. Existing customers remain top-level company nodes.
    op.add_column("companies", sa.Column("tenant_container_id", sa.String(64), nullable=True))
    op.add_column("companies", sa.Column("parent_company_id", sa.String(64), nullable=True))
    op.execute(sa.text("UPDATE companies SET tenant_container_id = id WHERE tenant_container_id IS NULL"))
    with op.batch_alter_table("companies") as batch:
        batch.drop_constraint("uq_companies_slug", type_="unique")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key(
            "fk_companies_tenant_container",
            "tenant_containers",
            ["tenant_container_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_companies_parent_same_container",
            "companies",
            ["tenant_container_id", "parent_company_id"],
            ["tenant_container_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint("uq_companies_container_id_id", ["tenant_container_id", "id"])
        batch.create_unique_constraint("uq_companies_container_slug", ["tenant_container_id", "slug"])
        batch.create_index("ix_companies_tenant_container_id", ["tenant_container_id"])

    # Stores must point to a company in the same tenant; container+store and
    # container+company+store keys are targetable by downstream scoped FKs.
    _add_tenant_column("stores")
    with op.batch_alter_table("stores") as batch:
        batch.drop_constraint("fk_stores_company", type_="foreignkey")
        batch.drop_constraint("uq_stores_company_code", type_="unique")
        batch.drop_index("ix_stores_company_active")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key(
            "fk_stores_tenant_container",
            "tenant_containers",
            ["tenant_container_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_stores_company_same_container",
            "companies",
            ["tenant_container_id", "company_id"],
            ["tenant_container_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint("uq_stores_container_id_id", ["tenant_container_id", "id"])
        batch.create_unique_constraint("uq_stores_container_company_id", ["tenant_container_id", "company_id", "id"])
        batch.create_unique_constraint("uq_stores_container_company_code", ["tenant_container_id", "company_id", "code"])
        batch.create_index("ix_stores_tenant_container_id", ["tenant_container_id"])
        batch.create_index("ix_stores_container_company_active", ["tenant_container_id", "company_id", "is_active"])

    # A user is a global login identity. Its role and permission set are now
    # copied into one explicit membership per tenant (super admins stay global).
    op.create_table(
        "container_memberships",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_container_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("company_id", sa.String(64), nullable=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_container_memberships_tenant_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_container_memberships_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_container_memberships_company", ondelete="RESTRICT"),
        sa.CheckConstraint(f"role IN ({VALID_ROLES})", name="ck_container_memberships_valid_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "user_id", name="uq_container_memberships_container_user"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_container_memberships_user_active", "container_memberships", ["user_id", "is_active"])
    op.execute(
        sa.text(
            "INSERT INTO container_memberships "
            "(id, tenant_container_id, user_id, company_id, role, permissions, is_default, is_active, created_at, updated_at) "
            "SELECT users.id, companies.tenant_container_id, users.id, users.company_id, users.role, users.permissions, 1, users.is_active, :now, :now "
            "FROM users JOIN companies ON companies.id = users.company_id "
            "WHERE users.company_id IS NOT NULL"
        ).bindparams(now=now)
    )

    # Every staff-to-store grant must reference a membership and a store in that
    # exact container. The company_id remains the owning operating company.
    _add_tenant_column("user_store_assignments")
    with op.batch_alter_table("user_store_assignments") as batch:
        batch.drop_constraint("fk_user_store_assignments_company", type_="foreignkey")
        batch.drop_constraint("fk_user_store_assignments_user_company", type_="foreignkey")
        batch.drop_constraint("fk_user_store_assignments_store_company", type_="foreignkey")
        batch.drop_index("ix_user_store_assignments_company_user")
        batch.drop_index("ix_user_store_assignments_company_store_active")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key(
            "fk_user_store_assignments_tenant_container",
            "tenant_containers",
            ["tenant_container_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_user_store_assignments_membership",
            "container_memberships",
            ["tenant_container_id", "user_id"],
            ["tenant_container_id", "user_id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_user_store_assignments_store_scope",
            "stores",
            ["tenant_container_id", "company_id", "store_id"],
            ["tenant_container_id", "company_id", "id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_user_store_assignments_container_user", ["tenant_container_id", "user_id"])
        batch.create_index("ix_user_store_assignments_container_store_active", ["tenant_container_id", "store_id", "is_active"])

    # Audit rows receive an immutable container key. A container-wide event may
    # omit company/store, but a store-scoped event cannot cross tenant ownership.
    op.add_column("audit_events", sa.Column("tenant_container_id", sa.String(64), nullable=True))
    op.execute(
        sa.text(
            "UPDATE audit_events SET tenant_container_id = "
            "(SELECT tenant_container_id FROM companies WHERE companies.id = audit_events.company_id) "
            "WHERE tenant_container_id IS NULL"
        )
    )
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_constraint("fk_audit_events_company", type_="foreignkey")
        batch.drop_constraint("fk_audit_events_store_company", type_="foreignkey")
        batch.drop_index("ix_audit_events_company_created")
        batch.drop_index("ix_audit_events_company_store_created")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.alter_column("company_id", existing_type=sa.String(64), nullable=True)
        batch.create_foreign_key(
            "fk_audit_events_tenant_container",
            "tenant_containers",
            ["tenant_container_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_audit_events_company_scope",
            "companies",
            ["tenant_container_id", "company_id"],
            ["tenant_container_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_audit_events_store_scope",
            "stores",
            ["tenant_container_id", "company_id", "store_id"],
            ["tenant_container_id", "company_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_audit_events_container_created", ["tenant_container_id", "created_at"])
        batch.create_index("ix_audit_events_container_store_created", ["tenant_container_id", "store_id", "created_at"])

    # Existing legacy import tables continue to retain company/store ownership,
    # now with an independently enforced container key.
    for table_name in LEGACY_TABLES:
        _add_tenant_column(table_name)
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
            batch.create_foreign_key(
                f"fk_{table_name}_tenant_container",
                "tenant_containers",
                ["tenant_container_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_foreign_key(
                f"fk_{table_name}_company_container",
                "companies",
                ["tenant_container_id", "company_id"],
                ["tenant_container_id", "id"],
                ondelete="CASCADE",
            )
            batch.create_foreign_key(
                f"fk_{table_name}_store_container",
                "stores",
                ["tenant_container_id", "company_id", "store_id"],
                ["tenant_container_id", "company_id", "id"],
                ondelete="RESTRICT",
            )
            batch.create_index(f"ix_{table_name}_tenant_container_id", ["tenant_container_id"])
            batch.drop_index(f"ix_{table_name}_company_store")
            batch.create_index(f"ix_{table_name}_company_store", ["tenant_container_id", "company_id", "store_id"])

    # Append container ownership to all Phase 3 records and replace their
    # company-only FKs with composite tenant/company/store/order constraints.
    _add_tenant_column("billing_series")
    with op.batch_alter_table("billing_series") as batch:
        batch.drop_constraint("fk_billing_series_company", type_="foreignkey")
        batch.drop_index("ix_billing_series_company_id")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key("fk_billing_series_tenant_container", "tenant_containers", ["tenant_container_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_billing_series_company_container", "companies", ["tenant_container_id", "company_id"], ["tenant_container_id", "id"], ondelete="CASCADE")
        batch.create_index("ix_billing_series_container_company", ["tenant_container_id", "company_id"])

    for table_name in ("daily_cashups", "sales_orders", "order_payments", "sales_order_lines", "order_removal_requests"):
        _add_tenant_column(table_name)

    with op.batch_alter_table("sales_orders") as batch:
        batch.drop_constraint("fk_sales_orders_company", type_="foreignkey")
        batch.drop_constraint("fk_sales_orders_origin_store_company", type_="foreignkey")
        batch.drop_index("ix_sales_orders_company_store_status")
        batch.drop_index("ix_sales_orders_phone_status_date")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key("fk_sales_orders_tenant_container", "tenant_containers", ["tenant_container_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_sales_orders_company_container", "companies", ["tenant_container_id", "company_id"], ["tenant_container_id", "id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_sales_orders_origin_store_container", "stores", ["tenant_container_id", "company_id", "origin_store_id"], ["tenant_container_id", "company_id", "id"], ondelete="RESTRICT")
        batch.create_unique_constraint("uq_sales_orders_container_company_id", ["tenant_container_id", "company_id", "id"])
        batch.create_index("ix_sales_orders_company_store_status", ["tenant_container_id", "company_id", "origin_store_id", "status"])
        batch.create_index("ix_sales_orders_phone_status_date", ["tenant_container_id", "company_id", "phone_search", "status", "business_date"])

    with op.batch_alter_table("sales_order_lines") as batch:
        batch.drop_constraint("fk_sales_order_lines_company", type_="foreignkey")
        batch.drop_constraint("fk_sales_order_lines_order_company", type_="foreignkey")
        batch.drop_constraint("fk_sales_order_lines_store_company", type_="foreignkey")
        batch.drop_index("ix_sales_order_lines_order_active")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key("fk_sales_order_lines_tenant_container", "tenant_containers", ["tenant_container_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_sales_order_lines_company_container", "companies", ["tenant_container_id", "company_id"], ["tenant_container_id", "id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_sales_order_lines_order_container", "sales_orders", ["tenant_container_id", "company_id", "order_id"], ["tenant_container_id", "company_id", "id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_sales_order_lines_store_container", "stores", ["tenant_container_id", "company_id", "added_store_id"], ["tenant_container_id", "company_id", "id"], ondelete="RESTRICT")
        batch.create_unique_constraint("uq_sales_order_lines_container_company_id", ["tenant_container_id", "company_id", "id"])
        batch.create_index("ix_sales_order_lines_order_active", ["tenant_container_id", "company_id", "order_id", "is_active"])

    with op.batch_alter_table("order_payments") as batch:
        batch.drop_constraint("fk_order_payments_company", type_="foreignkey")
        batch.drop_constraint("fk_order_payments_order_company", type_="foreignkey")
        batch.drop_constraint("fk_order_payments_store_company", type_="foreignkey")
        batch.drop_index("ix_order_payments_company_order")
        batch.drop_index("ix_order_payments_company_store_created")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key("fk_order_payments_tenant_container", "tenant_containers", ["tenant_container_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_order_payments_company_container", "companies", ["tenant_container_id", "company_id"], ["tenant_container_id", "id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_order_payments_order_container", "sales_orders", ["tenant_container_id", "company_id", "order_id"], ["tenant_container_id", "company_id", "id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_order_payments_store_container", "stores", ["tenant_container_id", "company_id", "store_id"], ["tenant_container_id", "company_id", "id"], ondelete="RESTRICT")
        batch.create_index("ix_order_payments_company_order", ["tenant_container_id", "company_id", "order_id"])
        batch.create_index("ix_order_payments_company_store_created", ["tenant_container_id", "company_id", "store_id", "created_at"])

    with op.batch_alter_table("daily_cashups") as batch:
        batch.drop_constraint("fk_daily_cashups_company", type_="foreignkey")
        batch.drop_constraint("fk_daily_cashups_store_company", type_="foreignkey")
        batch.drop_index("ix_daily_cashups_company_date_status")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key("fk_daily_cashups_tenant_container", "tenant_containers", ["tenant_container_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_daily_cashups_company_container", "companies", ["tenant_container_id", "company_id"], ["tenant_container_id", "id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_daily_cashups_store_container", "stores", ["tenant_container_id", "company_id", "store_id"], ["tenant_container_id", "company_id", "id"], ondelete="RESTRICT")
        batch.create_index("ix_daily_cashups_company_date_status", ["tenant_container_id", "company_id", "business_date", "status"])

    with op.batch_alter_table("order_removal_requests") as batch:
        batch.drop_constraint("fk_order_removal_requests_company", type_="foreignkey")
        batch.drop_constraint("fk_order_removal_requests_order_company", type_="foreignkey")
        batch.drop_constraint("fk_order_removal_requests_line_company", type_="foreignkey")
        batch.drop_constraint("fk_order_removal_requests_store_company", type_="foreignkey")
        batch.drop_index("ix_order_removal_requests_company_store_status")
        batch.alter_column("tenant_container_id", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key("fk_order_removal_requests_tenant_container", "tenant_containers", ["tenant_container_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_order_removal_requests_company_container", "companies", ["tenant_container_id", "company_id"], ["tenant_container_id", "id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_order_removal_requests_order_container", "sales_orders", ["tenant_container_id", "company_id", "order_id"], ["tenant_container_id", "company_id", "id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_order_removal_requests_line_container", "sales_order_lines", ["tenant_container_id", "company_id", "line_id"], ["tenant_container_id", "company_id", "id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_order_removal_requests_store_container", "stores", ["tenant_container_id", "company_id", "requesting_store_id"], ["tenant_container_id", "company_id", "id"], ondelete="RESTRICT")
        batch.create_index("ix_order_removal_requests_company_store_status", ["tenant_container_id", "company_id", "requesting_store_id", "status"])

    # Each domain starts at company-level sharing. This preserves today's single-
    # company behavior while preventing newly nested companies from sharing data
    # until the configured policy is deliberately changed by an authorized admin.
    op.create_table(
        "tenant_data_policies",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_container_id", sa.String(64), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("sharing_mode", sa.String(24), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("changed_by_user_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sharing_mode IN ('container', 'company', 'assigned_store', 'selected_units', 'disabled')", name="ck_tenant_data_policies_sharing_mode"),
        sa.CheckConstraint("domain IN ('product_catalog', 'inventory', 'customers', 'open_bills', 'sales', 'staff_accounts', 'suppliers', 'reports', 'files', 'audit', 'cashups', 'settings')", name="ck_tenant_data_policies_domain"),
        sa.ForeignKeyConstraint(["tenant_container_id"], ["tenant_containers.id"], name="fk_tenant_data_policies_container", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], name="fk_tenant_data_policies_changed_by", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "domain", name="uq_tenant_data_policies_container_domain"),
        sa.UniqueConstraint("tenant_container_id", "id", name="uq_tenant_data_policies_container_id_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_tenant_data_policies_container_enabled", "tenant_data_policies", ["tenant_container_id", "is_enabled"])
    # Seed a conservative company-only policy independently for every migrated
    # container. UUID() and SQLite randomblob() keep policy IDs unique while
    # preserving offline MySQL SQL generation and local migration tests.
    policy_id_expression = (
        "UUID()" if op.get_context().dialect.name == "mysql" else "lower(hex(randomblob(16)))"
    )
    for domain in DATA_DOMAINS:
        op.execute(
            sa.text(
                "INSERT INTO tenant_data_policies "
                "(id, tenant_container_id, domain, sharing_mode, is_enabled, policy_version, "
                "changed_by_user_id, created_at, updated_at) "
                f"SELECT {policy_id_expression}, tenant_container_id, :domain, 'company', 1, 1, NULL, :now, :now "
                "FROM companies"
            ).bindparams(domain=domain, now=now)
        )

    op.create_table(
        "tenant_data_policy_scopes",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_container_id", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("company_id", sa.String(64), nullable=True),
        sa.Column("store_id", sa.String(64), nullable=True),
        sa.Column("is_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(company_id IS NOT NULL AND store_id IS NULL) OR (company_id IS NULL AND store_id IS NOT NULL)", name="ck_tenant_data_policy_scopes_one_unit"),
        sa.ForeignKeyConstraint(["tenant_container_id", "policy_id"], ["tenant_data_policies.tenant_container_id", "tenant_data_policies.id"], name="fk_tenant_data_policy_scopes_policy", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"], name="fk_tenant_data_policy_scopes_company", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_container_id", "store_id"], ["stores.tenant_container_id", "stores.id"], name="fk_tenant_data_policy_scopes_store", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "policy_id", "company_id", "store_id", name="uq_tenant_data_policy_scopes_unit"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )


def downgrade():
    raise RuntimeError(
        "Refusing an automated tenant-container downgrade. Review container membership, policy, and data-scope changes, "
        "take a verified backup, then use a separately reviewed rollback plan."
    )
