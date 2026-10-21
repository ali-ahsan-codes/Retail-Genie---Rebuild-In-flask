"""Suppliers, supplier products, purchase orders, receiving, and logistics."""

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

SUPPLIER_STATUS_VALUES: tuple[str, ...] = ("active", "inactive")
PO_STATUS_VALUES: tuple[str, ...] = ("draft", "confirmed", "partially_received", "received", "cancelled")
PO_ATTACHMENT_TYPES: tuple[str, ...] = ("invoice", "shipping", "other")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(db.Model):
    """A company-scoped vendor supplying products."""

    __tablename__ = "scm_suppliers"
    __table_args__ = (
        CheckConstraint("supplier_status IN ('active', 'inactive')", name="ck_suppliers_status"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_suppliers_company_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_suppliers_container_company_id"),
        Index("ix_suppliers_container_company_active", "tenant_container_id", "company_id", "supplier_status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lead_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupplierProduct(db.Model):
    """A supplier's offered price for one company-owned catalog product."""

    __tablename__ = "scm_supplier_products"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_supplier_products_unit_price_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_supplier_products_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "supplier_id"],
            ["scm_suppliers.tenant_container_id", "scm_suppliers.company_id", "scm_suppliers.id"],
            name="fk_supplier_products_supplier",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_supplier_products_product",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_supplier_products_container_company_id"),
        UniqueConstraint("company_id", "supplier_id", "product_owner_company_id", "product_id", name="uq_supplier_products_supplier_product"),
        Index("ix_supplier_products_container_supplier", "tenant_container_id", "supplier_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_owner_company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_price: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    document_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupplierAttachment(db.Model):
    """A private file attached to one supplier record."""

    __tablename__ = "scm_supplier_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_supplier_attachments_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "supplier_id"],
            ["scm_suppliers.tenant_container_id", "scm_suppliers.company_id", "scm_suppliers.id"],
            name="fk_supplier_attachments_supplier",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_supplier_attachments_container_company_id"),
        Index("ix_supplier_attachments_container_supplier", "tenant_container_id", "supplier_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PurchaseOrder(db.Model):
    """A company-scoped purchase order with receiving and logistics status."""

    __tablename__ = "scm_purchase_orders"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed', 'partially_received', 'received', 'cancelled')", name="ck_purchase_orders_status"),
        CheckConstraint("total_amount >= 0", name="ck_purchase_orders_total_nonnegative"),
        CheckConstraint("advance_paid >= 0", name="ck_purchase_orders_advance_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_purchase_orders_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "supplier_id"],
            ["scm_suppliers.tenant_container_id", "scm_suppliers.company_id", "scm_suppliers.id"],
            name="fk_purchase_orders_supplier",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_purchase_orders_container_company_id"),
        UniqueConstraint("company_id", "po_number", name="uq_purchase_orders_company_number"),
        Index("ix_purchase_orders_company_status_created", "tenant_container_id", "company_id", "status", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    po_number: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    total_amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    advance_paid: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)
    transportation_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    logistics_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    received_store_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PurchaseOrderItem(db.Model):
    """One ordered product line on a purchase order."""

    __tablename__ = "scm_po_items"
    __table_args__ = (
        CheckConstraint("quantity_ordered > 0", name="ck_po_items_quantity_ordered_positive"),
        CheckConstraint("quantity_received >= 0", name="ck_po_items_quantity_received_nonnegative"),
        CheckConstraint("unit_price >= 0", name="ck_po_items_unit_price_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_po_items_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "po_id"],
            ["scm_purchase_orders.tenant_container_id", "scm_purchase_orders.company_id", "scm_purchase_orders.id"],
            name="fk_po_items_po_container",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_po_items_product",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_po_items_container_company_id"),
        Index("ix_po_items_container_po", "tenant_container_id", "po_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    po_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_owner_company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_price: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class PurchaseOrderAttachment(db.Model):
    """A private file attached to one purchase order."""

    __tablename__ = "scm_po_attachments"
    __table_args__ = (
        CheckConstraint("attachment_type IN ('invoice', 'shipping', 'other')", name="ck_po_attachments_type"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_po_attachments_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "po_id"],
            ["scm_purchase_orders.tenant_container_id", "scm_purchase_orders.company_id", "scm_purchase_orders.id"],
            name="fk_po_attachments_po_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_po_attachments_container_company_id"),
        Index("ix_po_attachments_container_po", "tenant_container_id", "po_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    po_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    attachment_type: Mapped[str] = mapped_column(String(24), nullable=False, default="other")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
