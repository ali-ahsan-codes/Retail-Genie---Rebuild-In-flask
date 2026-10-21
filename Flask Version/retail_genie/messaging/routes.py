"""Messaging pages and JSON APIs."""

from pathlib import Path

from flask import abort, current_app, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from ..extensions import db
from . import messaging_bp
from .service import (
    MessagingRuleError,
    authorized_attachment_path,
    conversation_dict,
    create_conversation,
    list_conversations,
    list_messages,
    mark_read,
    message_dict,
    recipient_suggestions,
    send_message,
)


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict(flat=True)


def _error(error: MessagingRuleError):
    return jsonify(error=error.code, message=str(error)), error.status_code


@messaging_bp.get("/messaging")
@login_required
def messaging_page():
    company_id = request.args.get("company_id")
    try:
        conversations = list_conversations(current_user, company_id=company_id)
        recipients = recipient_suggestions(current_user, company_id=company_id)
    except MessagingRuleError as error:
        abort(error.status_code)
    return render_template(
        "messaging/index.html",
        conversations=conversations,
        recipients=recipients,
        company_id=company_id,
    )


@messaging_bp.get("/messaging/compose")
@login_required
def compose_page():
    company_id = request.args.get("company_id")
    try:
        recipients = recipient_suggestions(current_user, company_id=company_id)
    except MessagingRuleError as error:
        abort(error.status_code)
    return render_template("messaging/compose.html", recipients=recipients, company_id=company_id)


@messaging_bp.get("/messaging/conversations")
@login_required
def conversations_api():
    try:
        conversations = list_conversations(current_user, company_id=request.args.get("company_id"))
    except MessagingRuleError as error:
        return _error(error)
    return jsonify({"conversations": conversations}), 200


@messaging_bp.post("/messaging/conversations")
@login_required
def create_conversation_api():
    data = _payload()
    recipient_ids = data.get("recipient_ids") or []
    if isinstance(recipient_ids, str):
        recipient_ids = [recipient_ids]
    try:
        conversation = create_conversation(
            current_user,
            subject=data.get("subject"),
            recipient_ids=[str(value) for value in recipient_ids],
            company_id=data.get("company_id") or None,
        )
        db.session.commit()
    except MessagingRuleError as error:
        db.session.rollback()
        return _error(error)
    if not request.is_json:
        return redirect(url_for("messaging.conversation_page", conversation_id=conversation.id))
    return jsonify({"conversation": conversation_dict(conversation)}), 201


@messaging_bp.get("/messaging/conversations/<string:conversation_id>")
@login_required
def conversation_page(conversation_id: str):
    try:
        messages = list_messages(current_user, conversation_id=conversation_id)
    except MessagingRuleError as error:
        abort(error.status_code)
    return render_template("messaging/thread.html", conversation_id=conversation_id, messages=messages)


@messaging_bp.get("/api/v1/messaging/conversations/<string:conversation_id>/messages")
@login_required
def conversation_messages_api(conversation_id: str):
    try:
        messages = list_messages(
            current_user,
            conversation_id=conversation_id,
            company_id=request.args.get("company_id"),
            after_id=request.args.get("after_id"),
        )
    except MessagingRuleError as error:
        return _error(error)
    return jsonify({"messages": messages}), 200


@messaging_bp.post("/messaging/conversations/<string:conversation_id>/messages")
@login_required
def send_message_api(conversation_id: str):
    data = _payload()
    attachments = request.files.getlist("attachments") if request.files else []
    try:
        message = send_message(
            current_user,
            conversation_id=conversation_id,
            content=data.get("content", ""),
            company_id=data.get("company_id") or None,
            attachments=attachments,
        )
        db.session.commit()
    except MessagingRuleError as error:
        db.session.rollback()
        return _error(error)
    if not request.is_json:
        return redirect(url_for("messaging.conversation_page", conversation_id=conversation_id))
    return jsonify({"message": message_dict(message)}), 201


@messaging_bp.get("/api/v1/messaging/attachments/<string:attachment_id>")
@login_required
def download_message_attachment_api(attachment_id: str):
    try:
        attachment, path = authorized_attachment_path(current_user, attachment_id=attachment_id)
    except MessagingRuleError as error:
        return _error(error)
    response = send_file(path, mimetype=attachment.mime_type or "application/octet-stream", as_attachment=True, download_name=attachment.original_name, conditional=True)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@messaging_bp.post("/api/v1/messaging/messages/<string:message_id>/read")
@login_required
def mark_message_read_api(message_id: str):
    data = _payload()
    try:
        mark_read(current_user, message_id=message_id, company_id=data.get("company_id") or None)
        db.session.commit()
    except MessagingRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"read": True}), 200


@messaging_bp.get("/api/v1/messaging/recipients")
@login_required
def recipient_suggestions_api():
    try:
        recipients = recipient_suggestions(
            current_user,
            search=request.args.get("q"),
            company_id=request.args.get("company_id"),
        )
    except MessagingRuleError as error:
        return _error(error)
    return jsonify({"recipients": recipients}), 200
