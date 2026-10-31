"""Administrator backup configuration and backup-run audit trail."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .user import utc_now


class BackupSettings(db.Model):
    __tablename__ = "backup_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_backup_settings_singleton"),
        CheckConstraint("interval_minutes BETWEEN 15 AND 10080", name="ck_backup_settings_interval"),
        CheckConstraint("retention_count BETWEEN 1 AND 365", name="ck_backup_settings_retention"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interval_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1440)
    retention_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=14)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def __repr__(self) -> str:
        return f"<BackupSettings enabled={self.enabled} interval_minutes={self.interval_minutes}>"


class BackupRun(db.Model):
    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_backup_runs_status"),
        CheckConstraint("trigger_type IN ('manual', 'scheduled')", name="ck_backup_runs_trigger_type"),
        Index("ix_backup_runs_status_requested_at", "status", "requested_at"),
        Index("ix_backup_runs_finished_at", "finished_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_by_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_retained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<BackupRun id={self.id!r} status={self.status!r} trigger={self.trigger_type!r}>"
