"""Add normalized, tenant-scoped catalog and store inventory ledger.

Revision ID: c3d91f4a7b26
Revises: ba2fd4c7e8a1
Create Date: 2026-10-18

Legacy product landing rows are preserved and copied into the operational catalog
and inventory tables. A per-product opening movement records the migrated stock.
"""

from alembic import op
import sqlalchemy as sa

revision = "c3d91f4a7b26"
down_revision = "ba2fd4c7e8a1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalog_products",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("barcode", sa.String(length=128), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("price", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("low_stock_price", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_demand_notice_product", sa.Boolean(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price IS NULL OR price >= 0", name="ck_catalog_products_price_nonnegative"),
        sa.CheckConstraint("low_stock_price IS NULL OR low_stock_price >= 0", name="ck_catalog_products_low_stock_price_nonnegative"),
        sa.CheckConstraint("is_active IN (0, 1)", name="ck_catalog_products_active_bool"),
        sa.CheckConstraint("is_demand_notice_product IN (0, 1)", name="ck_catalog_products_demand_notice_bool"),
        sa.ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_catalog_products_tenant_container_id_tenant_containers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id"], ["companies.tenant_container_id", "companies.id"],
            name="fk_catalog_products_company_container", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"],
            name="fk_catalog_products_created_by_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_catalog_products_tenant_company_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("catalog_products") as batch_op:
        batch_op.create_index(
            "ix_catalog_products_container_company_active",
            ["tenant_container_id", "company_id", "is_active"],
            unique=False,
        )
        batch_op.create_index(
            "ix_catalog_products_container_company_sku",
            ["tenant_container_id", "company_id", "sku"],
            unique=False,
        )
        batch_op.create_index(
            "ix_catalog_products_container_barcode",
            ["tenant_container_id", "barcode"],
            unique=False,
        )

    op.create_table(
        "inventory_balances",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=64), nullable=False),
        sa.Column("product_owner_company_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_inventory_balances_tenant_container_id_tenant_containers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_inventory_balances_store_scope", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_inventory_balances_product_scope", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["users.id"],
            name="fk_inventory_balances_updated_by_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_container_id", "company_id", "store_id", "product_owner_company_id", "product_id",
            name="uq_inventory_balances_store_product",
        ),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("inventory_balances") as batch_op:
        batch_op.create_index("ix_inventory_balances_container_store", ["tenant_container_id", "store_id"], unique=False)

    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=64), nullable=False),
        sa.Column("product_owner_company_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("movement_type", sa.String(length=24), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "movement_type IN ('opening', 'receive', 'adjustment', 'sale', 'return', 'transfer_in', 'transfer_out')",
            name="ck_inventory_movements_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_inventory_movements_tenant_container_id_tenant_containers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_inventory_movements_store_scope", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_inventory_movements_product_scope", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"],
            name="fk_inventory_movements_actor_user_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("inventory_movements") as batch_op:
        batch_op.create_index(
            "ix_inventory_movements_container_store_created",
            ["tenant_container_id", "store_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_inventory_movements_product_created",
            ["tenant_container_id", "product_id", "created_at"],
            unique=False,
        )

    bind = op.get_bind()
    op.execute(
        sa.text(
            """
            INSERT INTO catalog_products (
                id, tenant_container_id, company_id, sku, barcode, name, category,
                price, low_stock_price, expiry_date, is_demand_notice_product,
                image_url, is_active, created_by_id, created_at, updated_at
            )
            SELECT id, tenant_container_id, company_id, NULLIF(UPPER(TRIM(sku)), ''), NULL,
                   COALESCE(name, 'Unnamed product'), category, price, low_stock_price,
                   expiry_date, COALESCE(is_demand_notice_product, 0), image_url,
                   1, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM products
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO inventory_balances (
                id, tenant_container_id, company_id, store_id, product_owner_company_id,
                product_id, quantity_on_hand, low_stock_threshold, updated_by_id, created_at, updated_at
            )
            SELECT id, tenant_container_id, company_id, store_id, company_id,
                   id, COALESCE(quantity_in_stock, 0), low_stock_threshold, NULL,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM products
            """
        )
    )
    movement_id = "lower(hex(randomblob(16)))" if bind.dialect.name == "sqlite" else "UUID()"
    op.execute(
        sa.text(
            f"""
            INSERT INTO inventory_movements (
                id, tenant_container_id, company_id, store_id, product_owner_company_id,
                product_id, movement_type, quantity_delta, reason, actor_user_id, created_at
            )
            SELECT {movement_id}, tenant_container_id, company_id, store_id, company_id,
                   id, 'opening', COALESCE(quantity_in_stock, 0),
                   'Opening balance migrated from legacy product landing table', NULL, CURRENT_TIMESTAMP
            FROM products
            """
        )
    )


def downgrade():
    bind = op.get_bind()
    for table_name in ("inventory_movements", "inventory_balances", "catalog_products"):
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        if count:
            raise RuntimeError(
                f"Refusing to drop non-empty {table_name}; preserve product and inventory data before downgrade."
            )
    op.drop_index("ix_inventory_movements_product_created", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_container_store_created", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index("ix_inventory_balances_container_store", table_name="inventory_balances")
    op.drop_table("inventory_balances")
    op.drop_index("ix_catalog_products_container_barcode", table_name="catalog_products")
    op.drop_index("ix_catalog_products_container_company_sku", table_name="catalog_products")
    op.drop_index("ix_catalog_products_container_company_active", table_name="catalog_products")
    op.drop_table("catalog_products")
