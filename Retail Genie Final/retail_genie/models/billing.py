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
    JSON,
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
ORDER_DELIVERY_STATUSES: tuple[str, ...] = ("pending", "partially_delivered", "delivered", "cancelled")
RETURN_KINDS: tuple[str, ...] = ("refund", "exchange", "store_credit")


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


class OrderNumberSeries(db.Model):
    """Company-level monotonic series for a bill reference allocated at creation."""

    __tablename__ = "order_number_series"
    __table_args__ = (
        CheckConstraint("next_number > 0", name="ck_order_number_series_positive_next"),
        CheckConstraint("length(trim(prefix)) > 0", name="ck_order_number_series_nonempty_prefix"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_order_number_series_company_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("company_id", name="uq_order_number_series_company"),
        UniqueConstraint("company_id", "prefix", name="uq_order_number_series_company_prefix"),
        Index("ix_order_number_series_container_company", "tenant_container_id", "company_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prefix: Mapped[str] = mapped_column(String(24), nullable=False, default="ORD-")
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SalesOrder(db.Model):
    __tablename__ = "sales_orders"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed', 'voided')", name="ck_sales_orders_status"),
        CheckConstraint(
            "delivery_status IN ('pending', 'partially_delivered', 'delivered', 'cancelled')",
            name="ck_sales_orders_delivery_status",
        ),
        CheckConstraint("total_amount >= 0", name="ck_sales_orders_total_nonnegative"),
        CheckConstraint("subtotal_amount >= 0", name="ck_sales_orders_subtotal_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="ck_sales_orders_discount_nonnegative"),
        CheckConstraint(
            "applied_discount_percentage >= 0 AND applied_discount_percentage <= 100",
            name="ck_sales_orders_discount_pct_range",
        ),
        CheckConstraint(
            "applied_global_discount_percentage >= 0 AND applied_global_discount_percentage <= 100",
            name="ck_sales_orders_global_discount_pct_range",
        ),
        CheckConstraint("invoice_category IS NULL OR invoice_category IN ('cash', 'bank', 'bank_transfer', 'other')", name="ck_sales_orders_invoice_category"),
        CheckConstraint(
            "source_demand_notice_id IS NULL OR source_quotation_id IS NULL",
            name="ck_sales_orders_one_commercial_source",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "source_demand_notice_id"],
            ["commercial_demand_notices.tenant_container_id", "commercial_demand_notices.company_id", "commercial_demand_notices.id"],
            name="fk_sales_orders_source_demand_notice",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "source_quotation_id"],
            ["commercial_quotations.tenant_container_id", "commercial_quotations.company_id", "commercial_quotations.id"],
            name="fk_sales_orders_source_quotation",
            ondelete="RESTRICT",
        ),
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
        UniqueConstraint("company_id", "order_number", name="uq_sales_orders_company_order_number"),
        UniqueConstraint("company_id", "invoice_number", name="uq_sales_orders_company_invoice"),
        UniqueConstraint("company_id", "source_quotation_id", name="uq_sales_orders_source_quotation"),
        UniqueConstraint("company_id", "checkout_idempotency_key", name="uq_sales_orders_company_checkout_idempotency"),
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
    order_number: Mapped[str] = mapped_column(String(64), nullable=False)
    source_demand_notice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_quotation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_return_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checkout_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checkout_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subtotal_amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    discount_amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    applied_discount_percentage: Mapped[object] = mapped_column(Numeric(12, 8), nullable=False, default=0)
    applied_global_discount_percentage: Mapped[object] = mapped_column(Numeric(12, 8), nullable=False, default=0)
    taxes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    storekeeper_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cashier_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reminder_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reminder_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_salesperson_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    secondary_salesperson_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    primary_commission_rate: Mapped[object | None] = mapped_column(Numeric(12, 8), nullable=True)
    secondary_commission_rate: Mapped[object | None] = mapped_column(Numeric(12, 8), nullable=True)
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
        CheckConstraint(
            "(product_owner_company_id IS NULL AND product_id IS NULL) OR "
            "(product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)",
            name="ck_sales_order_lines_product_link_pair",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_sales_order_lines_catalog_product",
            ondelete="RESTRICT",
        ),
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
    product_owner_company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_order_payments_container_company_id"),
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


class OrderReturn(db.Model):
    """Append-only return transaction for one or more lines on a settled order."""

    __tablename__ = "order_returns"
    __table_args__ = (
        CheckConstraint("kind IN ('refund', 'exchange', 'store_credit')", name="ck_order_returns_kind"),
        CheckConstraint("refund_method IN ('cash', 'bank', 'bank_transfer', 'other')", name="ck_order_returns_refund_method"),
        CheckConstraint("refund_amount > 0", name="ck_order_returns_refund_amount_positive"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_order_returns_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "order_id"],
            ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"],
            name="fk_order_returns_order_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_order_returns_store_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "idempotency_key", name="uq_order_returns_company_idempotency"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_order_returns_container_company_id"),
        Index("ix_order_returns_company_order_created", "tenant_container_id", "company_id", "order_id", "created_at"),
        Index("ix_order_returns_company_store_created", "tenant_container_id", "company_id", "store_id", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="refund")
    refund_method: Mapped[str] = mapped_column(String(24), nullable=False)
    refund_amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    transaction_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class StoreCredit(db.Model):
    """Credit issued to a customer and redeemable against later bills."""

    __tablename__ = "store_credits"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_store_credits_amount_positive"),
        CheckConstraint("remaining_amount >= 0", name="ck_store_credits_remaining_nonnegative"),
        CheckConstraint("remaining_amount <= amount", name="ck_store_credits_remaining_range"),
        CheckConstraint("status IN ('open', 'fully_used', 'expired', 'voided')", name="ck_store_credits_status"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_store_credits_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "source_order_id"],
            ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"],
            name="fk_store_credits_source_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "source_return_id"],
            ["order_returns.tenant_container_id", "order_returns.company_id", "order_returns.id"],
            name="fk_store_credits_source_return",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "credit_number", name="uq_store_credits_company_number"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_store_credits_container_company_id"),
        Index("ix_store_credits_company_phone", "tenant_container_id", "company_id", "phone_search"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    credit_number: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_search: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    remaining_amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_return_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issued_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class OrderReturnLine(db.Model):
    __tablename__ = "order_return_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_return_lines_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_return_lines_unit_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="ck_order_return_lines_total_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "return_id"],
            ["order_returns.tenant_container_id", "order_returns.company_id", "order_returns.id"],
            name="fk_order_return_lines_return_container",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "sales_order_line_id"],
            ["sales_order_lines.tenant_container_id", "sales_order_lines.company_id", "sales_order_lines.id"],
            name="fk_order_return_lines_order_line_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "return_id", "sales_order_line_id", name="uq_order_return_lines_return_line"),
        Index("ix_order_return_lines_container_line", "tenant_container_id", "company_id", "sales_order_line_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    return_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sales_order_line_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    line_total: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class StoreCreditRedemption(db.Model):
    """Auditable tender redemption for a credit against a later sale."""

    __tablename__ = "store_credit_redemptions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_store_credit_redemptions_amount_positive"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_credit_id"],
            ["store_credits.tenant_container_id", "store_credits.company_id", "store_credits.id"],
            name="fk_store_credit_redemptions_credit",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "order_id"],
            ["sales_orders.tenant_container_id", "sales_orders.company_id", "sales_orders.id"],
            name="fk_store_credit_redemptions_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "payment_id"],
            ["order_payments.tenant_container_id", "order_payments.company_id", "order_payments.id"],
            name="fk_store_credit_redemptions_payment",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "idempotency_key", name="uq_store_credit_redemptions_company_idempotency"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_store_credit_redemptions_container_company_id"),
        Index("ix_store_credit_redemptions_container_credit", "tenant_container_id", "store_credit_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_credit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    processed_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DailyCashup(db.Model):
    __tablename__ = "daily_cashups"
    __table_args__ = (
        CheckConstraint("status IN ('submitted', 'approved', 'rejected')", name="ck_daily_cashups_status"),
        CheckConstraint(
            "counted_cash >= 0 AND counted_bank >= 0 AND counted_bank_transfer >= 0 AND counted_other >= 0",
            name="ck_daily_cashups_counted_amounts_nonnegative",
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
