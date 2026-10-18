"""Add a durable scoped event feed for authorized realtime updates.

Revision ID: d7a4c261f9e3
Revises: c3d91f4a7b26
Create Date: 2026-10-18
"""

from alembic import op
import sqlalchemy as sa

revision = "d7a4c261f9e3"
down_revision = "c3d91f4a7b26"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "realtime_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("tenant_container_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=64), nullable=False),
        sa.Column("product_owner_company_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_realtime_events_tenant_container_id_tenant_containers", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_realtime_events_store_scope", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_realtime_events_product_scope", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"],
            name="fk_realtime_events_actor_user_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_realtime_events_container_store_cursor",
        "realtime_events",
        ["tenant_container_id", "store_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_realtime_events_container_product_cursor",
        "realtime_events",
        ["tenant_container_id", "product_id", "id"],
        unique=False,
    )


def downgrade():
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM realtime_events")).scalar_one()
    if count:
        raise RuntimeError("Refusing to drop non-empty realtime_events; event replay history must be retained.")
    op.drop_index("ix_realtime_events_container_product_cursor", table_name="realtime_events")
    op.drop_index("ix_realtime_events_container_store_cursor", table_name="realtime_events")
    op.drop_table("realtime_events")
