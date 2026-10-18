"""Store-scoped orders, split payments, approval requests, invoice series, and cashups."""

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

PAYMENT_METHODS: tuple[str, ...] = ("cash", "bank", "bank_transfer", "other")
INVOICE_CATEGORIES: tuple[str, ...] = PAYMENT_METHODS
ORDER_STATUSES: tuple[str, ...] = ("open", "closed", "voided")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BillingSeries(db.Model):
    __tablename__ = "billing_series"
    __table_args__ = (
        CheckConstraint("category IN ('cash', 'bank', 'bank_transfer', 'other')", name="ck_billing_series_category"),
        CheckConstraint("next_number > 0", name="ck_billing_series_positive_next"),
        CheckConstraint("length(trim(prefix)) > 0", name="ck_billing_series_nonempty_prefix"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_billing_series_company_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("company_id", "category", name="uq_billing_series_company_category"),
        UniqueConstraint("company_id", "prefix", name="uq_billing_series_company_prefix"),
        UniqueConstraint("company_id", "id", name="uq_billing_series_company_id_id"),
        Index("ix_billing_series_container_company", "tenant_container_id", "company_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SalesOrder(db.Model):
    __tablename__ = "sales_orders"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed', 'voided')", name="ck_sales_orders_status"),
        CheckConstraint("total_amount >= 0", name="ck_sales_orders_total_nonnegative"),
        CheckConstraint("invoice_category IS NULL OR invoice_category IN ('cash', 'bank', 'bank_transfer', 'other')", name="ck_sales_orders_invoice_category"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_sales_orders_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "origin_store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_sales_orders_origin_store_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_sales_orders_company_id_id"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_sales_orders_container_company_id"),
        UniqueConstraint("company_id", "invoice_number", name="uq_sales_orders_company_invoice"),
        Index("ix_sales_orders_phone_status_date", "tenant_container_id", "company_id", "phone_search", "status", "business_date"),
        Index("ix_sales_orders_company_store_status", "tenant_container_id", "company_id", "origin_store_id", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    origin_store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_search: Mapped[str] = mapped_column(String(32), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    total_amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    invoice_category: Mapped[str | None] = mapped_column(String(24), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SalesOrderLine(db.Model):
    __tablename__ = "sales_order_lines"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_sales_order_lines_quantity_nonnegative"),
        CheckConstraint("unit_price >= 0", name="ck_sales_order_lines_unit_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="ck_sales_order_lines_line_total_nonnegative"),
        CheckConstraint("(is_active = 1 AND quantity > 0) OR (is_active = 0 AND quantity = 0)", name="ck_sales_order_lines_quantity_active"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_sales_order_lines_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "order_id"],
            ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"],
            name="fk_sales_order_lines_order_container",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "added_store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_sales_order_lines_store_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_sales_order_lines_company_id_id"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_sales_order_lines_container_company_id"),
        Index("ix_sales_order_lines_order_active", "tenant_container_id", "company_id", "order_id", "is_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    added_store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    line_total: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    removal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class OrderPayment(db.Model):
    __tablename__ = "order_payments"
    __table_args__ = (
        CheckConstraint("method IN ('cash', 'bank', 'bank_transfer', 'other')", name="ck_order_payments_method"),
        CheckConstraint("amount > 0", name="ck_order_payments_amount_positive"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_order_payments_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "order_id"],
            ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"],
            name="fk_order_payments_order_container",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_order_payments_store_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "idempotency_key", name="uq_order_payments_company_idempotency"),
        Index("ix_order_payments_company_store_created", "tenant_container_id", "company_id", "store_id", "created_at"),
        Index("ix_order_payments_company_order", "tenant_container_id", "company_id", "order_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transaction_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    received_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OrderRemovalRequest(db.Model):
    __tablename__ = "order_removal_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_order_removal_requests_status"),
        CheckConstraint("quantity_to_remove > 0", name="ck_order_removal_requests_quantity_positive"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_order_removal_requests_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "order_id"],
            ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"],
            name="fk_order_removal_requests_order_container",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "line_id"],
            ["sales_order_lines.tenant_container_id", "sales_order_lines.company_id", "sales_order_lines.id"],
            name="fk_order_removal_requests_line_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "requesting_store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_order_removal_requests_store_container",
            ondelete="RESTRICT",
        ),
        Index("ix_order_removal_requests_company_store_status", "tenant_container_id", "company_id", "requesting_store_id", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    line_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requesting_store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_to_remove: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    requested_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DailyCashup(db.Model):
    __tablename__ = "daily_cashups"
    __table_args__ = (
        CheckConstraint("status IN ('submitted', 'approved', 'rejected')", name="ck_daily_cashups_status"),
        CheckConstraint(
            "expected_cash >= 0 AND expected_bank >= 0 AND expected_bank_transfer >= 0 AND expected_other >= 0 "
            "AND counted_cash >= 0 AND counted_bank >= 0 AND counted_bank_transfer >= 0 AND counted_other >= 0",
            name="ck_daily_cashups_amounts_nonnegative",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_daily_cashups_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_daily_cashups_store_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "store_id", "business_date", name="uq_daily_cashups_store_day"),
        Index("ix_daily_cashups_company_date_status", "tenant_container_id", "company_id", "business_date", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    submitted_by_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    expected_cash: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    expected_bank: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    expected_bank_transfer: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    expected_other: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    counted_cash: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    counted_bank: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    counted_bank_transfer: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    counted_other: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="submitted")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def variances(self) -> dict[str, object]:
        return {
            "cash": self.counted_cash - self.expected_cash,
            "bank": self.counted_bank - self.expected_bank,
            "bank_transfer": self.counted_bank_transfer - self.expected_bank_transfer,
            "other": self.counted_other - self.expected_other,
        }
