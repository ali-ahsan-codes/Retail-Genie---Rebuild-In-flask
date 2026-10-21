"""Counted stock audits with evidence images."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
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

STOCK_AUDIT_STATUSES: tuple[str, ...] = ("draft", "in_progress", "completed", "cancelled")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StockAudit(db.Model):
    """A store-scoped counting exercise assigned to one auditor."""

    __tablename__ = "stock_audits"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'in_progress', 'completed', 'cancelled')", name="ck_stock_audits_status"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_stock_audits_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_stock_audits_store_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stock_audits_container_company_id"),
        UniqueConstraint("company_id", "audit_number", name="uq_stock_audits_company_number"),
        Index("ix_stock_audits_company_store_status", "tenant_container_id", "company_id", "store_id", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_number: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    store_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    admin_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    auditor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    auditor_selfie_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class StockAuditItem(db.Model):
    """One product line under audit with its expected and final counts."""

    __tablename__ = "stock_audit_items"
    __table_args__ = (
        CheckConstraint("current_stock >= 0", name="ck_stock_audit_items_current_stock_nonnegative"),
        CheckConstraint("final_audited_qty IS NULL OR final_audited_qty >= 0", name="ck_stock_audit_items_final_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_stock_audit_items_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "audit_id"],
            ["stock_audits.tenant_container_id", "stock_audits.company_id", "stock_audits.id"],
            name="fk_stock_audit_items_audit_container",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_stock_audit_items_product",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stock_audit_items_container_company_id"),
        UniqueConstraint("company_id", "audit_id", "product_id", name="uq_stock_audit_items_audit_product"),
        Index("ix_stock_audit_items_container_audit", "tenant_container_id", "audit_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_owner_company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_audited_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class StockAuditItemCount(db.Model):
    """An append-only count event recorded while an audit is in progress."""

    __tablename__ = "stock_audit_item_counts"
    __table_args__ = (
        CheckConstraint("count >= 0", name="ck_stock_audit_item_counts_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_stock_audit_item_counts_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "audit_item_id"],
            ["stock_audit_items.tenant_container_id", "stock_audit_items.company_id", "stock_audit_items.id"],
            name="fk_stock_audit_item_counts_item_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stock_audit_item_counts_container_company_id"),
        Index("ix_stock_audit_item_counts_container_item", "tenant_container_id", "audit_item_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    counted_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class StockAuditImage(db.Model):
    """Evidence captured against one count event."""

    __tablename__ = "stock_audit_images"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_stock_audit_images_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "count_event_id"],
            ["stock_audit_item_counts.tenant_container_id", "stock_audit_item_counts.company_id", "stock_audit_item_counts.id"],
            name="fk_stock_audit_images_count_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_stock_audit_images_container_company_id"),
        Index("ix_stock_audit_images_container_count", "tenant_container_id", "count_event_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    count_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
