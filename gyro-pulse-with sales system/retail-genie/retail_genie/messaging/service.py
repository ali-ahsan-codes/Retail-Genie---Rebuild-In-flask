"""Container-scoped internal messaging rules."""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from flask import current_app
from sqlalchemy import select

from ..auth.tenant_context import current_tenant_container_id
from ..extensions import db
from ..models import (
    AuditEvent,
    ContainerMembership,
    Company,
    Conversation,
    Message,
    MessageAttachment,
    MessageRecipient,
    TenantContainer,
    User,
)

MAX_MESSAGE_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_MESSAGE_LENGTH = 8000


def _audit(actor: User, conversation: Conversation, *, action: str, entity_id: str) -> None:
    db.session.add(AuditEvent(
        tenant_container_id=conversation.tenant_container_id,
        company_id=conversation.company_id,
        actor_user_id=actor.id,
        action=action,
        entity_type="Conversation" if action.endswith("conversation.created") else "Message",
        entity_id=entity_id,
        after_data={"conversation_id": conversation.id},
    ))


class MessagingRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _tenant_for_actor(actor: User) -> str:
    tenant_id = current_tenant_container_id(actor)
    if not tenant_id:
        raise MessagingRuleError("Select an active tenant container first.", 403, "tenant_forbidden")
    container = db.session.get(TenantContainer, tenant_id)
    if container is None or not container.is_active:
        raise MessagingRuleError("Tenant container not found.", 404, "not_found")
    return tenant_id


def _container_members(user_id: str, tenant_container_id: str) -> ContainerMembership | None:
    return db.session.execute(
        select(ContainerMembership).where(
            ContainerMembership.user_id == user_id,
            ContainerMembership.tenant_container_id == tenant_container_id,
            ContainerMembership.is_active.is_(True),
        )
    ).scalar_one_or_none()


def conversation_dict(conversation: Conversation, *, actor: User | None = None) -> dict:
    unread = 0
    if actor is not None:
        unread = (
            db.session.execute(
                select(MessageRecipient.id)
                .join(Message, Message.id == MessageRecipient.message_id)
                .where(
                    MessageRecipient.tenant_container_id == conversation.tenant_container_id,
                    MessageRecipient.recipient_id == actor.id,
                    MessageRecipient.read_at.is_(None),
                    Message.conversation_id == conversation.id,
                    Message.sender_id != actor.id,
                )
            )
            .scalars()
            .all()
        )
        unread = len(unread)
    return {
        "id": conversation.id,
        "subject": conversation.subject,
        "creator_id": conversation.creator_id,
        "company_id": conversation.company_id,
        "created_at": conversation.created_at.isoformat().replace("+00:00", "Z") if conversation.created_at else None,
        "unread_count": unread,
    }


def message_dict(message: Message) -> dict:
    attachments = db.session.execute(
        select(MessageAttachment).where(
            MessageAttachment.tenant_container_id == message.tenant_container_id,
            MessageAttachment.company_id == message.company_id,
            MessageAttachment.message_id == message.id,
        ).order_by(MessageAttachment.uploaded_at.asc())
    ).scalars()
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "content": message.content,
        "sent_at": message.sent_at.isoformat().replace("+00:00", "Z") if message.sent_at else None,
        "attachments": [
            {
                "id": attachment.id,
                "original_name": attachment.original_name,
                "mime_type": attachment.mime_type,
            }
            for attachment in attachments
        ],
    }


def list_conversations(actor: User, *, company_id: str | None = None) -> list[dict]:
    tenant_id = _tenant_for_actor(actor)
    statement = select(Conversation).where(Conversation.tenant_container_id == tenant_id)
    if company_id:
        statement = statement.where(Conversation.company_id == company_id)
    # Participant membership is stored on the thread, not inferred from a
    # tenant-wide message recipient list. Bound the scan to avoid an unbounded
    # endpoint while keeping private conversations isolated.
    statement = statement.order_by(Conversation.created_at.desc()).limit(5000)
    rows = db.session.execute(statement).scalars()
    return [conversation_dict(row, actor=actor) for row in rows if actor.id in (row.participant_ids or [])][:200]


def create_conversation(actor: User, *, subject: str | None, recipient_ids: list[str], company_id: str | None = None) -> Conversation:
    tenant_id = _tenant_for_actor(actor)
    actor_membership = _container_members(actor.id, tenant_id)
    if not actor.is_super_admin and actor_membership is None:
        raise MessagingRuleError("You are not a member of this tenant.", 403, "tenant_forbidden")
    if company_id:
        company = db.session.execute(select(Company).where(Company.id == company_id, Company.tenant_container_id == tenant_id, Company.is_active.is_(True))).scalar_one_or_none()
        if company is None or (not actor.is_super_admin and actor_membership.company_id != company.id):
            raise MessagingRuleError("Company not found.", 404, "not_found")
    cleaned_subject = (str(subject or "").strip()[:160]) or None
    if not isinstance(recipient_ids, list) or not recipient_ids or len(recipient_ids) > 50:
        raise MessagingRuleError("Provide 1-50 recipients.")
    recipients: list[str] = []
    for raw in recipient_ids:
        user_id = str(raw)
        if user_id == actor.id:
            continue
        membership = _container_members(user_id, tenant_id)
        if membership is None:
            raise MessagingRuleError("Every recipient must be a member of this tenant.", 403, "recipient_not_in_tenant")
        if company_id and membership.company_id != company_id:
            raise MessagingRuleError("Recipients must belong to the selected company.", 403, "recipient_not_in_company")
        if user_id not in recipients:
            recipients.append(user_id)
    if not recipients:
        raise MessagingRuleError("Provide at least one recipient.")
    conversation = Conversation(
        tenant_container_id=tenant_id,
        company_id=company_id,
        subject=cleaned_subject,
        participant_ids=[actor.id, *recipients],
        creator_id=actor.id,
    )
    db.session.add(conversation)
    db.session.flush()
    _audit(actor, conversation, action="messaging.conversation.created", entity_id=conversation.id)
    return conversation


def _conversation_for_actor(actor: User, conversation_id: str, *, company_id: str | None = None) -> Conversation:
    tenant_id = _tenant_for_actor(actor)
    conversation = db.session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_container_id == tenant_id,
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise MessagingRuleError("Conversation not found.", 404, "not_found")
    if company_id and conversation.company_id != company_id:
        raise MessagingRuleError("Conversation not found.", 404, "not_found")
    membership = _container_members(actor.id, tenant_id)
    if membership is None and not actor.is_super_admin:
        raise MessagingRuleError("You are not a member of this tenant.", 403, "tenant_forbidden")
    if actor.id not in (conversation.participant_ids or []):
        raise MessagingRuleError("You are not a participant in this conversation.", 403, "permission_denied")
    return conversation


def send_message(actor: User, *, conversation_id: str, content: str, company_id: str | None = None, attachments: list = None) -> Message:
    conversation = _conversation_for_actor(actor, conversation_id, company_id=company_id)
    cleaned_content = str(content or "").strip()
    if not cleaned_content:
        raise MessagingRuleError("Message content is required.")
    if len(cleaned_content) > MAX_MESSAGE_LENGTH:
        raise MessagingRuleError(f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer.")
    message = Message(
        tenant_container_id=conversation.tenant_container_id,
        company_id=conversation.company_id,
        conversation_id=conversation.id,
        sender_id=actor.id,
        content=cleaned_content,
    )
    db.session.add(message)
    db.session.flush()
    _audit(actor, conversation, action="messaging.message.sent", entity_id=message.id)
    # Deliver only to persisted conversation participants, never all tenant users.
    participant_ids = [user_id for user_id in (conversation.participant_ids or []) if user_id != actor.id]
    for user_id in participant_ids:
        db.session.add(
            MessageRecipient(
                tenant_container_id=conversation.tenant_container_id,
                company_id=conversation.company_id,
                message_id=message.id,
                recipient_id=user_id,
                recipient_type="user",
            )
        )
    for file_storage in attachments or []:
        relative_path = _store_message_attachment(file_storage, namespace=f"messaging/{conversation.id}")
        db.session.add(
            MessageAttachment(
                tenant_container_id=conversation.tenant_container_id,
                company_id=conversation.company_id,
                message_id=message.id,
                file_path=relative_path,
                original_name=os.path.basename((file_storage.filename or "attachment").replace("\\", "/")),
                mime_type=file_storage.mimetype,
            )
        )
    db.session.flush()
    return message


def list_messages(actor: User, *, conversation_id: str, company_id: str | None = None, after_id: str | None = None) -> list[dict]:
    conversation = _conversation_for_actor(actor, conversation_id, company_id=company_id)
    statement = select(Message).where(
        Message.tenant_container_id == conversation.tenant_container_id,
        Message.conversation_id == conversation.id,
    )
    if after_id:
        statement = statement.where(Message.id > after_id)
    statement = statement.order_by(Message.sent_at.asc()).limit(500)
    return [message_dict(message) for message in db.session.execute(statement).scalars()]


def authorized_attachment_path(actor: User, *, attachment_id: str) -> tuple[MessageAttachment, Path]:
    tenant_id = _tenant_for_actor(actor)
    attachment = db.session.execute(
        select(MessageAttachment).where(
            MessageAttachment.id == attachment_id,
            MessageAttachment.tenant_container_id == tenant_id,
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise MessagingRuleError("Attachment not found.", 404, "not_found")
    message = db.session.execute(
        select(Message).where(
            Message.id == attachment.message_id,
            Message.tenant_container_id == tenant_id,
        )
    ).scalar_one_or_none()
    if message is None:
        raise MessagingRuleError("Attachment not found.", 404, "not_found")
    _conversation_for_actor(actor, message.conversation_id)
    root = Path(current_app.config["UPLOADS_DIR"]).resolve()
    path = (root / attachment.file_path).resolve()
    if root not in path.parents or not path.is_file():
        raise MessagingRuleError("Attachment is missing from private storage.", 404, "file_missing")
    return attachment, path


def mark_read(actor: User, *, message_id: str, company_id: str | None = None) -> Message | None:
    message = db.session.execute(
        select(Message).where(Message.id == message_id)
    ).scalar_one_or_none()
    if message is None:
        raise MessagingRuleError("Message not found.", 404, "not_found")
    conversation = _conversation_for_actor(actor, message.conversation_id, company_id=company_id)
    recipient = db.session.execute(
        select(MessageRecipient).where(
            MessageRecipient.tenant_container_id == conversation.tenant_container_id,
            MessageRecipient.message_id == message.id,
            MessageRecipient.recipient_id == actor.id,
        )
    ).scalar_one_or_none()
    if recipient is None:
        raise MessagingRuleError("You are not a recipient of this message.", 403, "permission_denied")
    if recipient.read_at is None:
        recipient.read_at = datetime.now(timezone.utc)
        db.session.flush()
    return message


def _store_message_attachment(file_storage, *, namespace: str) -> str:
    if file_storage is None or not getattr(file_storage, "filename", None):
        raise MessagingRuleError("Choose a file to attach.")
    original_name = os.path.basename(file_storage.filename.replace("\\", "/"))
    if not original_name or len(original_name) > 255:
        raise MessagingRuleError("The file name must be 1-255 characters.")
    size = len(file_storage.read() or b"")
    file_storage.stream.seek(0)
    if size <= 0 or size > MAX_MESSAGE_ATTACHMENT_BYTES:
        raise MessagingRuleError("Message attachments must be between 1 byte and 10 MB.")
    relative_path = f"{namespace}/{uuid4().hex[:12]}_{original_name}"
    destination = os.path.join(current_app.config["UPLOADS_DIR"], relative_path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    file_storage.save(destination)
    return relative_path


def recipient_suggestions(actor: User, *, search: str | None = None, company_id: str | None = None) -> list[dict]:
    tenant_id = _tenant_for_actor(actor)
    statement = (
        select(User.username, User.id, ContainerMembership.role)
        .join(
            ContainerMembership,
            (ContainerMembership.user_id == User.id)
            & (ContainerMembership.tenant_container_id == tenant_id)
            & (ContainerMembership.is_active.is_(True)),
        )
        .where(User.is_active.is_(True))
    )
    if company_id:
        statement = statement.where(ContainerMembership.company_id == company_id)
    cleaned_search = (search or "").strip()
    if cleaned_search:
        statement = statement.where(User.username.ilike(f"%{cleaned_search}%"))
    statement = statement.order_by(User.username.asc()).limit(50)
    return [
        {"id": user_id, "username": username, "role": role}
        for username, user_id, role in db.session.execute(statement).all()
    ]
