"""Tenant-scoped demand notices and customer quotations."""

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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BusinessNumberSeries(db.Model):
    """Company-level counters used for human-readable commercial documents."""

    __tablename__ = "business_number_series"
    __table_args__ = (
        CheckConstraint("document_type IN ('demand_notice', 'quotation')", name="ck_business_number_series_type"),
        CheckConstraint("next_number > 0", name="ck_business_number_series_next_positive"),
        CheckConstraint("length(trim(prefix)) > 0", name="ck_business_number_series_prefix_nonempty"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_business_number_series_company_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("company_id", "document_type", name="uq_business_number_series_company_type"),
        UniqueConstraint("company_id", "prefix", name="uq_business_number_series_company_prefix"),
        Index("ix_business_number_series_container_company", "tenant_container_id", "company_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_type: Mapped[str] = mapped_column(String(24), nullable=False)
    prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class DemandNotice(db.Model):
    """A store-scoped customer request, optionally tied to a known product."""

    __tablename__ = "commercial_demand_notices"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'converted', 'cancelled')", name="ck_commercial_demand_notices_status"),
        CheckConstraint("quantity_requested > 0", name="ck_commercial_demand_notices_quantity_positive"),
        CheckConstraint(
            "quantity_fulfilled >= 0 AND quantity_fulfilled <= quantity_requested",
            name="ck_commercial_demand_notices_fulfilled_range",
        ),
        CheckConstraint("agreed_price IS NULL OR agreed_price >= 0", name="ck_commercial_demand_notices_price_nonnegative"),
        CheckConstraint(
            "(product_owner_company_id IS NULL AND product_id IS NULL) OR "
            "(product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)",
            name="ck_commercial_demand_notices_product_pair",
        ),
        CheckConstraint("is_new_product IN (0, 1)", name="ck_commercial_demand_notices_new_product_bool"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_commercial_demand_notices_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_commercial_demand_notices_store_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_commercial_demand_notices_catalog_product",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "notice_number", name="uq_commercial_demand_notices_company_number"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_commercial_demand_notices_container_company_id"),
        Index("ix_commercial_demand_notices_store_status_date", "tenant_container_id", "company_id", "store_id", "status", "created_at"),
        Index("ix_commercial_demand_notices_phone", "tenant_container_id", "company_id", "phone_search"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    notice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    salesperson_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_search: Mapped[str] = mapped_column(String(32), nullable=False)
    product_owner_company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_fulfilled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agreed_price: Mapped[object | None] = mapped_column(Numeric(14, 3), nullable=True)
    expected_availability_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    is_new_product: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class Quotation(db.Model):
    """Price proposal with immutable product/price snapshots on each line."""

    __tablename__ = "commercial_quotations"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'sent', 'accepted', 'rejected', 'cancelled', 'expired', 'converted')", name="ck_commercial_quotations_status"),
        CheckConstraint("preparation_days >= 0", name="ck_commercial_quotations_preparation_nonnegative"),
        CheckConstraint("total_amount >= 0", name="ck_commercial_quotations_total_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_commercial_quotations_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_commercial_quotations_store_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "quotation_number", name="uq_commercial_quotations_company_number"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_commercial_quotations_container_company_id"),
        Index("ix_commercial_quotations_store_status_created", "tenant_container_id", "company_id", "store_id", "status", "created_at"),
        Index("ix_commercial_quotations_phone", "tenant_container_id", "company_id", "customer_phone"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quotation_number: Mapped[str] = mapped_column(String(64), nullable=False)
    salesperson_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    preparation_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    total_amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class QuotationLine(db.Model):
    __tablename__ = "commercial_quotation_lines"
    __table_args__ = (
        CheckConstraint("line_number > 0", name="ck_commercial_quotation_lines_number_positive"),
        CheckConstraint("quantity > 0", name="ck_commercial_quotation_lines_quantity_positive"),
        CheckConstraint("unit_price > 0", name="ck_commercial_quotation_lines_price_positive"),
        CheckConstraint("line_total > 0", name="ck_commercial_quotation_lines_total_positive"),
        CheckConstraint(
            "(is_external = 1 AND product_owner_company_id IS NULL AND product_id IS NULL) OR "
            "(is_external = 0 AND product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)",
            name="ck_commercial_quotation_lines_external_product_pair",
        ),
        CheckConstraint("is_external IN (0, 1)", name="ck_commercial_quotation_lines_external_bool"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "quotation_id"],
            ["commercial_quotations.tenant_container_id", "commercial_quotations.company_id", "commercial_quotations.id"],
            name="fk_commercial_quotation_lines_quotation_container",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_commercial_quotation_lines_catalog_product",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "quotation_id", "line_number", name="uq_commercial_quotation_lines_quote_number"),
        Index("ix_commercial_quotation_lines_quote", "tenant_container_id", "company_id", "quotation_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quotation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_owner_company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit_price: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    converted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
