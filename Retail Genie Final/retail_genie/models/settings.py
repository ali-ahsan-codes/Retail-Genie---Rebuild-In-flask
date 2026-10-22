"""Company-scoped operational settings ported from the legacy app."""

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


class TaxSetting(db.Model):
    """A named tax rate a company can apply to sales documents."""

    __tablename__ = "settings_tax"
    __table_args__ = (
        CheckConstraint("rate >= 0", name="ck_tax_settings_rate_nonnegative"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_tax_settings_company_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_tax_settings_container_company_id"),
        UniqueConstraint("company_id", "name", name="uq_tax_settings_company_name"),
        Index("ix_tax_settings_container_company", "tenant_container_id", "company_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    rate: Mapped[object] = mapped_column(Numeric(12, 8), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class CommissionSetting(db.Model):
    """Sales-target commission configuration; one active row per company."""

    __tablename__ = "settings_commission"
    __table_args__ = (
        CheckConstraint("sales_target >= 0", name="ck_commission_settings_target_nonnegative"),
        CheckConstraint("commission_percentage >= 0", name="ck_commission_settings_percentage_nonnegative"),
        CheckConstraint("commission_interval IN ('daily', 'weekly', 'monthly')", name="ck_commission_settings_interval"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_commission_settings_company_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_commission_settings_container_company_id"),
        Index("ix_commission_settings_container_company", "tenant_container_id", "company_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sales_target: Mapped[object] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    commission_interval: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    commission_percentage: Mapped[object] = mapped_column(Numeric(12, 8), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class GlobalDiscountSetting(db.Model):
    """A dated company-wide discount applied automatically at order creation."""

    __tablename__ = "settings_global_discount"
    __table_args__ = (
        CheckConstraint("percentage >= 0 AND percentage <= 100", name="ck_global_discount_settings_percentage_range"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_global_discount_settings_company_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_global_discount_settings_container_company_id"),
        Index("ix_global_discount_settings_container_company", "tenant_container_id", "company_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    percentage: Mapped[object] = mapped_column(Numeric(12, 8), nullable=False, default=0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class AttendanceSetting(db.Model):
    """Punch-in enforcement and concurrent-break limits for one company."""

    __tablename__ = "settings_attendance"
    __table_args__ = (
        CheckConstraint("max_concurrent_breaks >= 1", name="ck_attendance_settings_breaks_positive"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_attendance_settings_company_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_attendance_settings_container_company_id"),
        UniqueConstraint("tenant_container_id", "company_id", name="uq_attendance_settings_company"),
        Index("ix_attendance_settings_container_company", "tenant_container_id", "company_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mandatory_attendance_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_mandatory_attendance_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_concurrent_breaks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ProductCategory(db.Model):
    """An administered category name inside one company's catalog."""

    __tablename__ = "product_categories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_product_categories_company_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_product_categories_container_company_id"),
        UniqueConstraint("company_id", "name", name="uq_product_categories_company_name"),
        Index("ix_product_categories_container_company", "tenant_container_id", "company_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
