"""Durable, tenant-scoped event feed used for realtime delivery and replay."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RealtimeEvent(db.Model):
    """Committed business event; clients replay by cursor after reconnecting."""

    __tablename__ = "realtime_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "store_id"],
            ["stores.tenant_container_id", "stores.company_id", "stores.id"],
            name="fk_realtime_events_store_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "product_owner_company_id", "product_id"],
            ["catalog_products.tenant_container_id", "catalog_products.company_id", "catalog_products.id"],
            name="fk_realtime_events_product_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_realtime_events_container_store_cursor", "tenant_container_id", "store_id", "id"),
        Index("ix_realtime_events_container_product_cursor", "tenant_container_id", "product_id", "id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_owner_company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
