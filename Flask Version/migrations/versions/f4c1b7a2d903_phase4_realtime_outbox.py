"""Generalize the durable event feed for Phase 4 multi-worker delivery."""

from alembic import op
import sqlalchemy as sa

revision = "f4c1b7a2d903"
down_revision = "e18b6a904f31"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "realtime_events",
        sa.Column("domain", sa.String(length=32), nullable=False, server_default="inventory"),
    )
    op.add_column("realtime_events", sa.Column("recipient_user_id", sa.String(length=64), nullable=True))
    op.add_column("realtime_events", sa.Column("cursor_floor", sa.BigInteger(), nullable=True))
    op.add_column("inventory_movements", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index(
        "uq_inventory_movement_actor_idempotency",
        "inventory_movements",
        ["tenant_container_id", "actor_user_id", "idempotency_key"],
        unique=True,
    )
    with op.batch_alter_table("realtime_events") as batch:
        batch.alter_column("company_id", existing_type=sa.String(length=64), nullable=True)
        batch.alter_column("store_id", existing_type=sa.String(length=64), nullable=True)
        batch.alter_column("product_owner_company_id", existing_type=sa.String(length=64), nullable=True)
        batch.alter_column("product_id", existing_type=sa.String(length=64), nullable=True)
        batch.create_foreign_key(
            "fk_realtime_events_recipient_user_id_users",
            "users",
            ["recipient_user_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_index(
        "ix_realtime_events_recipient_cursor",
        "realtime_events",
        ["recipient_user_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_realtime_events_domain_cursor",
        "realtime_events",
        ["tenant_container_id", "domain", "id"],
        unique=False,
    )


def downgrade():
    bind = op.get_bind()
    generic_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM realtime_events "
            "WHERE domain <> 'inventory' OR recipient_user_id IS NOT NULL OR cursor_floor IS NOT NULL "
            "OR company_id IS NULL OR store_id IS NULL "
            "OR product_owner_company_id IS NULL OR product_id IS NULL"
        )
    ).scalar_one()
    idempotency_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM inventory_movements WHERE idempotency_key IS NOT NULL")
    ).scalar_one()
    if generic_count or idempotency_count:
        raise RuntimeError("Refusing to remove Phase 4 realtime rows, idempotency keys, or generalized event scope.")
    op.drop_index("ix_realtime_events_domain_cursor", table_name="realtime_events")
    op.drop_index("ix_realtime_events_recipient_cursor", table_name="realtime_events")
    op.drop_index("uq_inventory_movement_actor_idempotency", table_name="inventory_movements")
    op.drop_column("inventory_movements", "idempotency_key")
    with op.batch_alter_table("realtime_events") as batch:
        batch.drop_constraint("fk_realtime_events_recipient_user_id_users", type_="foreignkey")
        batch.alter_column("company_id", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("store_id", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("product_owner_company_id", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("product_id", existing_type=sa.String(length=64), nullable=False)
        batch.drop_column("cursor_floor")
        batch.drop_column("recipient_user_id")
        batch.drop_column("domain")
