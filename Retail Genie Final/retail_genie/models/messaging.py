"""Container-scoped internal messaging."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db

RECIPIENT_TYPES: tuple[str, ...] = ("user", "role")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(db.Model):
    """A message thread inside one tenant container."""

    __tablename__ = "messaging_conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_conversations_company_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_conversations_container_company_id"),
        Index("ix_conversations_container_created", "tenant_container_id", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(160), nullable=True)
    participant_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    creator_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Message(db.Model):
    """One message inside a conversation."""

    __tablename__ = "messaging_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_messages_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "conversation_id"],
            ["messaging_conversations.tenant_container_id", "messaging_conversations.company_id", "messaging_conversations.id"],
            name="fk_messages_conversation_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_messages_container_company_id"),
        Index("ix_messages_container_conversation_sent", "tenant_container_id", "conversation_id", "sent_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class MessageRecipient(db.Model):
    """Delivery and read state for one message recipient."""

    __tablename__ = "messaging_message_recipients"
    __table_args__ = (
        CheckConstraint("recipient_type IN ('user', 'role')", name="ck_message_recipients_type"),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_message_recipients_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "message_id"],
            ["messaging_messages.tenant_container_id", "messaging_messages.company_id", "messaging_messages.id"],
            name="fk_message_recipients_message_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_message_recipients_container_company_id"),
        Index("ix_message_recipients_container_recipient", "tenant_container_id", "recipient_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageAttachment(db.Model):
    """A private file attached to one message."""

    __tablename__ = "messaging_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id"],
            ["companies.tenant_container_id", "companies.id"],
            name="fk_attachments_company_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_container_id", "company_id", "message_id"],
            ["messaging_messages.tenant_container_id", "messaging_messages.company_id", "messaging_messages.id"],
            name="fk_attachments_message_container",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_container_id", "company_id", "id", name="uq_attachments_container_company_id"),
        Index("ix_attachments_container_message", "tenant_container_id", "message_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_container_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant_containers.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
