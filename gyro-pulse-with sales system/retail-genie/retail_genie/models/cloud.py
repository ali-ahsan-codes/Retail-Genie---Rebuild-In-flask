"""Personal and shared cloud files inside one tenant container."""

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

CLOUD_SHARE_SCOPE: tuple[str, ...] = ("container", "company", "store", "user")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CloudFile(db.Model):
    """An uploaded file owned by one account inside one container."""

    __tablename__ = "cloud_files"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_cloud_files_size_nonnegative"),
        CheckConstraint("share_scope IN ('container', 'company', 'store', 'user')", name="ck_cloud_files_share_scope"),
        ForeignKeyConstraint(
            ["tenant_container_id", "owner_company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_cloud_files_owner_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "id", name="uq_cloud_files_container_id"),
        Index("ix_cloud_files_container_owner", "tenant_container_id", "owner_user_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner_company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    share_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    share_unit_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class CloudFileShare(db.Model):
    """An explicit per-user grant on a shared file."""

    __tablename__ = "cloud_file_shares"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_cloud_file_shares_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "file_id"],
            ["cloud_files.tenant_container_id", "cloud_files.id"],
            name="fk_cloud_file_shares_file_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "file_id", "shared_with_user_id", name="uq_cloud_file_shares_file_user"),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_cloud_file_shares_container_company_id"),
        Index("ix_cloud_file_shares_container_recipient", "tenant_container_id", "shared_with_user_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_id: Mapped[str] = mapped_column(String(64), nullable=False)
    shared_with_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
