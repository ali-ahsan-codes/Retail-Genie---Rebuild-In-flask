"""Platform-managed SaaS plans, tenant subscriptions, and change requests."""

from datetime import date, datetime, timezone
from decimal import Decimal
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

SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "suspended", "canceled")
PLAN_CHANGE_STATUSES = ("pending", "approved", "rejected", "canceled")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SubscriptionPlan(db.Model):
    """A platform price tier; prices are OMR and usage caps are nullable/unlimited."""

    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint("monthly_price >= 0", name="ck_subscription_plans_nonnegative_price"),
        CheckConstraint("max_companies IS NULL OR max_companies >= 1", name="ck_subscription_plans_company_limit"),
        CheckConstraint("max_stores IS NULL OR max_stores >= 1", name="ck_subscription_plans_store_limit"),
        CheckConstraint("max_active_users IS NULL OR max_active_users >= 1", name="ck_subscription_plans_user_limit"),
        UniqueConstraint("code", name="uq_subscription_plans_code"),
        Index("ix_subscription_plans_active_sort", "is_active", "sort_order"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    monthly_price: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    max_companies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_stores: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_active_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class TenantSubscription(db.Model):
    """One current platform-managed subscription per independent tenant."""

    __tablename__ = "tenant_subscriptions"
    __table_args__ = (
        CheckConstraint("status IN ('trialing', 'active', 'past_due', 'suspended', 'canceled')", name="ck_tenant_subscriptions_status"),
        ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_tenant_subscriptions_container", ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", name="uq_tenant_subscriptions_container"),
        UniqueConstraint("tenant_container_id", "id", name="uq_tenant_subscriptions_container_id"),
        Index("ix_tenant_subscriptions_status_period", "status", "current_period_end"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="trialing")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class SubscriptionInvoice(db.Model):
    """Manual OMR subscription invoice; no payment gateway is assumed."""

    __tablename__ = "subscription_invoices"
    __table_args__ = (
        CheckConstraint("amount_due >= 0", name="ck_subscription_invoices_nonnegative_amount"),
        CheckConstraint("status IN ('open', 'paid', 'void')", name="ck_subscription_invoices_status"),
        CheckConstraint("period_end > period_start", name="ck_subscription_invoices_valid_period"),
        ForeignKeyConstraint(
            ["tenant_container_id", "subscription_id"],
            ["tenant_subscriptions.tenant_container_id", "tenant_subscriptions.id"],
            name="fk_subscription_invoices_scoped_subscription",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("subscription_id", "period_start", name="uq_subscription_invoices_subscription_period"),
        UniqueConstraint("invoice_number", name="uq_subscription_invoices_number"),
        Index("ix_subscription_invoices_tenant_status_due", "tenant_container_id", "status", "due_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="RESTRICT"), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(48), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="OMR", server_default="OMR")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PlatformAuditEvent(db.Model):
    """Audit log for global plan-catalog and SaaS billing administration."""

    __tablename__ = "platform_audit_events"
    __table_args__ = (
        Index("ix_platform_audit_created", "created_at"),
        Index("ix_platform_audit_entity", "entity_type", "entity_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tenant_container_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)


class PlanChangeRequest(db.Model):
    """A tenant admin request; platform staff explicitly reviews and applies it."""

    __tablename__ = "plan_change_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'canceled')", name="ck_plan_change_requests_status"),
        ForeignKeyConstraint(
            ["tenant_container_id"], ["tenant_containers.id"],
            name="fk_plan_change_requests_container", ondelete="CASCADE",
        ),
        Index("ix_plan_change_requests_tenant_status_created", "tenant_container_id", "status", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    request_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
