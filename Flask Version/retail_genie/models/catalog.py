"""Normalized product catalog and store-level inventory ledger."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db

INVENTORY_MOVEMENT_TYPES: tuple[str, ...] = (
    "opening",
    "receive",
    "adjustment",
    "sale",
    "return",
    "transfer_in",
    "transfer_out",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CatalogProduct(db.Model):
    """A canonical company-owned product; stock remains store-specific."""

    __tablename__ = "catalog_products"
    __table_args__ = (
        CheckConstraint("price IS NULL OR price >= 0", name="ck_catalog_products_price_nonnegative"),
        CheckConstraint("low_stock_price IS NULL OR low_stock_price >= 0", name="ck_catalog_products_low_stock_price_nonnegative"),
        CheckConstraint("is_active IN (0, 1)", name="ck_catalog_products_active_bool"),
        CheckConstraint("is_demand_notice_product IN (0, 1)", name="ck_catalog_products_demand_notice_bool"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_catalog_products_company_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_catalog_products_tenant_company_id"),
        Index("ix_catalog_products_container_company_active", "tenant_container_id", "company_id", "is_active"),
        Index("ix_catalog_products_container_company_sku", "tenant_container_id", "company_id", "sku"),
        Index("ix_catalog_products_container_barcode", "tenant_container_id", "barcode"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price: Mapped[object | None] = mapped_column(Numeric(14, 3), nullable=True)
    low_stock_price: Mapped[object | None] = mapped_column(Numeric(14, 3), nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demand_notice_product: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class InventoryBalance(db.Model):
    """Current on-hand quantity for a canonical product at one store."""

    __tablename__ = "inventory_balances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_inventory_balances_store_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_inventory_balances_product_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_container_id",
            "company_id",
            "store_id",
            "product_owner_company_id",
            "product_id",
            name="uq_inventory_balances_store_product",
        ),
        Index("ix_inventory_balances_container_store", "tenant_container_id", "store_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_owner_company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class InventoryMovement(db.Model):
    """Append-only stock movement entry used for audit and reconciliation."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('opening', 'receive', 'adjustment', 'sale', 'return', 'transfer_in', 'transfer_out')",
            name="ck_inventory_movements_type",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_inventory_movements_store_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_inventory_movements_product_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_inventory_movements_container_store_created", "tenant_container_id", "store_id", "created_at"),
        Index("ix_inventory_movements_product_created", "tenant_container_id", "product_id", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_owner_company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
