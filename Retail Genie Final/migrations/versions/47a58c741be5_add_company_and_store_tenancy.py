"""Add company/store scope, staff assignments, and audit events.

Revision ID: 47a58c741be5
Revises: 183163e6fa51
Create Date: 2026-10-18

Existing Phase 2 data is placed in one default company and store. The importer
must specify a company/store when the target contains more than one.
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "47a58c741be5"
down_revision = "183163e6fa51"
branch_labels = None
depends_on = None

DEFAULT_COMPANY_ID = "retail-genie-default-company"
DEFAULT_STORE_ID = "retail-genie-default-store"
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


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_companies_slug"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "stores",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("company_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_stores_company", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "code", name="uq_stores_company_code"),
        sa.UniqueConstraint("company_id", "id", name="uq_stores_company_id_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_stores_company_active", "stores", ["company_id", "is_active"])

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        sa.table(
            "companies",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("slug", sa.String),
            sa.column("timezone", sa.String),
            sa.column("is_active", sa.Boolean),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [{
            "id": DEFAULT_COMPANY_ID,
            "name": "Default Company",
            "slug": "default-company",
            "timezone": "Asia/Muscat",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }],
    )
    op.bulk_insert(
        sa.table(
            "stores",
            sa.column("id", sa.String),
            sa.column("company_id", sa.String),
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("is_active", sa.Boolean),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [{
            "id": DEFAULT_STORE_ID,
            "company_id": DEFAULT_COMPANY_ID,
            "code": "MAIN",
            "name": "Main Store",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }],
    )

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("company_id", sa.String(64), nullable=True))
        batch.create_index("ix_users_company_id", ["company_id"])
        batch.create_unique_constraint("uq_users_company_id_id", ["company_id", "id"])
        batch.create_foreign_key("fk_users_company", "companies", ["company_id"], ["id"], ondelete="CASCADE")
        batch.drop_constraint("ck_users_valid_role", type_="check")
        batch.create_check_constraint(
            "ck_users_valid_role",
            "role IN ('super_admin', 'company_admin', 'admin', 'manager', 'salesperson', 'storekeeper', 'cashier', 'logistics', 'auditor', 'display', 'express')",
        )
    op.execute(
        sa.text("UPDATE users SET company_id = :company_id WHERE company_id IS NULL AND role != 'super_admin'")
        .bindparams(company_id=DEFAULT_COMPANY_ID)
    )

    # Every legacy business row is explicitly scoped to the migrated company and
    # default store before constraints become active.
    for table_name in LEGACY_TABLES:
        op.add_column(table_name, sa.Column("company_id", sa.String(64), nullable=True))
        op.add_column(table_name, sa.Column("store_id", sa.String(64), nullable=True))
        op.execute(
            sa.text(
                f'UPDATE "{table_name}" SET company_id = :company_id, store_id = :store_id '
                "WHERE company_id IS NULL"
            ).bindparams(company_id=DEFAULT_COMPANY_ID, store_id=DEFAULT_STORE_ID)
        )
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column("company_id", existing_type=sa.String(64), nullable=False)
            batch.create_foreign_key(
                f"fk_{table_name}_company",
                "companies",
                ["company_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_foreign_key(
                f"fk_{table_name}_store_company",
                "stores",
                ["company_id", "store_id"],
                ["company_id", "id"],
                ondelete="RESTRICT",
            )
            batch.create_index(f"ix_{table_name}_company_id", ["company_id"])
            batch.create_index(f"ix_{table_name}_company_store", ["company_id", "store_id"])

    op.create_table(
        "user_store_assignments",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("company_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("assigned_by_id", sa.String(64), nullable=True),
        sa.Column("can_view_shared_bills", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"], name="fk_user_store_assignments_assigned_by", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_user_store_assignments_company", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "user_id"], ["users.company_id", "users.id"], name="fk_user_store_assignments_user_company", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "store_id"], ["stores.company_id", "stores.id"], name="fk_user_store_assignments_store_company", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "store_id", name="uq_user_store_assignments_user_store"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_user_store_assignments_company_user", "user_store_assignments", ["company_id", "user_id"])
    op.create_index("ix_user_store_assignments_company_store_active", "user_store_assignments", ["company_id", "store_id", "is_active"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("company_id", sa.String(64), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=True),
        sa.Column("actor_user_id", sa.String(64), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_audit_events_actor", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_audit_events_company", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "store_id"], ["stores.company_id", "stores.id"], name="fk_audit_events_store_company", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_audit_events_company_created", "audit_events", ["company_id", "created_at"])
    op.create_index("ix_audit_events_company_store_created", "audit_events", ["company_id", "store_id", "created_at"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])

    # Carry all previously provisioned staff into the only existing store. Shared
    # cross-store bill access is intentionally not granted by migration. Reusing
    # the user ID as this seed assignment ID is deterministic and SQL-portable.
    op.execute(
        sa.text(
            "INSERT INTO user_store_assignments "
            "(id, company_id, user_id, store_id, assigned_by_id, can_view_shared_bills, is_active, created_at, updated_at) "
            "SELECT id, company_id, id, :store_id, NULL, 0, 1, :created_at, :updated_at "
            "FROM users WHERE company_id IS NOT NULL"
        ).bindparams(store_id=DEFAULT_STORE_ID, created_at=now, updated_at=now)
    )


def downgrade():
    connection = op.get_bind()
    extra_company_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM companies WHERE id != :company_id").bindparams(company_id=DEFAULT_COMPANY_ID)
    ).scalar_one()
    extra_store_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM stores WHERE id != :store_id").bindparams(store_id=DEFAULT_STORE_ID)
    ).scalar_one()
    audit_count = connection.execute(sa.text("SELECT COUNT(*) FROM audit_events")).scalar_one()
    shared_bill_grants = connection.execute(
        sa.text("SELECT COUNT(*) FROM user_store_assignments WHERE can_view_shared_bills = 1")
    ).scalar_one()
    if extra_company_count or extra_store_count or audit_count or shared_bill_grants:
        raise RuntimeError("Refusing destructive tenant downgrade: export data and use a reviewed rollback plan instead.")
    for table_name in LEGACY_TABLES:
        other_tenant_rows = connection.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table_name}" WHERE company_id != :company_id').bindparams(company_id=DEFAULT_COMPANY_ID)
        ).scalar_one()
        if other_tenant_rows:
            raise RuntimeError("Refusing to remove tenant keys while company-scoped business rows exist.")

    for table_name in reversed(LEGACY_TABLES):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_index(f"ix_{table_name}_company_store")
            batch.drop_index(f"ix_{table_name}_company_id")
            batch.drop_constraint(f"fk_{table_name}_store_company", type_="foreignkey")
            batch.drop_constraint(f"fk_{table_name}_company", type_="foreignkey")
            batch.drop_column("store_id")
            batch.drop_column("company_id")

    op.drop_table("user_store_assignments")
    op.drop_table("audit_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_valid_role", type_="check")
    op.execute("UPDATE users SET role = 'admin' WHERE role IN ('super_admin', 'company_admin')")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_company", type_="foreignkey")
        batch.drop_index("ix_users_company_id")
        batch.drop_constraint("uq_users_company_id_id", type_="unique")
        batch.create_check_constraint(
            "ck_users_valid_role",
            "role IN ('admin', 'manager', 'salesperson', 'storekeeper', 'cashier', 'logistics', 'auditor', 'display', 'express')",
        )
        batch.drop_column("company_id")
    op.drop_index("ix_stores_company_active", table_name="stores")
    op.drop_table("stores")
    op.drop_table("companies")
