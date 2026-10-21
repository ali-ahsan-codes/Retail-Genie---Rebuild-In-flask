"""Attendance punch logs and staff break records."""

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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db

ATTENDANCE_METHODS: tuple[str, ...] = ("auto", "manual", "selfie")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AttendanceLog(db.Model):
    """One clock-in event per staff member per business day."""

    __tablename__ = "hr_attendance_logs"
    __table_args__ = (
        CheckConstraint("method IN ('auto', 'manual', 'selfie')", name="ck_attendance_logs_method"),
        CheckConstraint("clock_out_at IS NULL OR clock_out_at > timestamp", name="ck_attendance_logs_clockout_order"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_attendance_logs_company_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_attendance_logs_container_company_id"),
        UniqueConstraint("tenant_container_id", "company_id", "user_id", "attendance_date", name="uq_attendance_logs_company_user_day"),
        Index("ix_attendance_logs_container_company_date", "tenant_container_id", "company_id", "attendance_date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attendance_date: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    selfie_data_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    selfie_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    clock_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class BreakLog(db.Model):
    """A staff break window; at most the configured concurrent count per user."""

    __tablename__ = "hr_break_logs"
    __table_args__ = (
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_break_logs_duration_nonnegative"),
        CheckConstraint("end_time IS NULL OR end_time >= start_time", name="ck_break_logs_end_order"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_break_logs_company_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_break_logs_container_company_id"),
        Index("ix_break_logs_container_user_start", "tenant_container_id", "user_id", "start_time"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
