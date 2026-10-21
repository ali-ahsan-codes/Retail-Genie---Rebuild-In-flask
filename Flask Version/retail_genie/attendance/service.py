"""Attendance punch-in/out and break rules."""

from __future__ import annotations

import base64
import binascii
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from flask import current_app
from sqlalchemy import func, select

from ..auth.tenant_context import current_tenant_container_id
from ..extensions import db
from ..models import AttendanceLog, AttendanceSetting, AuditEvent, BreakLog, Company, TenantContainer, User

DATA_URI_PATTERN = re.compile(r"^data:(image/(?:png|jpe?g|gif|webp));base64,([A-Za-z0-9+/=]+)$")
MAX_SELFIE_BYTES = 3 * 1024 * 1024


class AttendanceRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _tenant_for_actor(actor: User) -> str:
    tenant_id = current_tenant_container_id(actor)
    if not tenant_id:
        raise AttendanceRuleError("Select an active tenant container first.", 403, "tenant_forbidden")
    container = db.session.get(TenantContainer, tenant_id)
    if container is None or not container.is_active:
        raise AttendanceRuleError("Tenant container not found.", 404, "not_found")
    return tenant_id


def _company_for_actor(actor: User, company_id: str | None) -> Company:
    from ..auth.tenant_context import current_membership

    tenant_id = _tenant_for_actor(actor)
    if actor.is_super_admin:
        if not company_id:
            raise AttendanceRuleError("Select a company for this operation.", 400, "company_required")
        company = db.session.get(Company, company_id)
        if company is None or company.tenant_container_id != tenant_id or not company.is_active:
            raise AttendanceRuleError("Company not found.", 404, "not_found")
        return company
    membership = current_membership(actor, tenant_container_id=tenant_id)
    if membership is None or not membership.company_id:
        raise AttendanceRuleError("Company not found.", 404, "not_found")
    if company_id and company_id != membership.company_id:
        raise AttendanceRuleError("Company not found.", 404, "not_found")
    company = db.session.get(Company, membership.company_id)
    if company is None or not company.is_active:
        raise AttendanceRuleError("Company not found.", 404, "not_found")
    return company


def _audit_attendance(actor: User, company: Company, *, action: str, entity_type: str, entity_id: str, after: dict) -> None:
    db.session.add(AuditEvent(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        actor_user_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        after_data=after,
    ))


def _business_date(company: Company, moment: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        zone = ZoneInfo(company.timezone)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return moment.astimezone(zone).date().isoformat()


def _store_selfie(selfie_data_uri: str | None, *, log_id: str, user_id: str) -> tuple[str | None, str | None]:
    """Persist a data-URI selfie under the private uploads directory."""
    if not selfie_data_uri:
        return None, None
    if not isinstance(selfie_data_uri, str) or len(selfie_data_uri) > MAX_SELFIE_BYTES * 2:
        raise AttendanceRuleError("The selfie is too large.")
    match = DATA_URI_PATTERN.match(selfie_data_uri.strip())
    if match is None:
        raise AttendanceRuleError("The selfie must be a base64 PNG, JPEG, GIF, or WebP image.")
    mime_type, encoded = match.group(1), match.group(2)
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise AttendanceRuleError("The selfie image data is invalid.") from None
    if not image_bytes or len(image_bytes) > MAX_SELFIE_BYTES:
        raise AttendanceRuleError("The selfie is too large.")
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}[mime_type]
    relative_path = f"attendance/{log_id}_{user_id}.{extension}"
    destination = os.path.join(current_app.config["UPLOADS_DIR"], relative_path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "wb") as handle:
        handle.write(image_bytes)
    return None, relative_path


def clock_in(actor: User, *, company_id: str | None = None, method: str = "auto", selfie_data_uri: str | None = None) -> AttendanceLog:
    """Record one punch-in per user per company business day."""
    if not actor.is_authenticated:
        raise AttendanceRuleError("Sign in to record attendance.", 401, "authentication_required")
    if method not in {"auto", "manual", "selfie"}:
        raise AttendanceRuleError("Unknown attendance method.")
    company = _company_for_actor(actor, company_id)
    moment = datetime.now(timezone.utc)
    business_date = _business_date(company, moment)
    existing = db.session.execute(
        select(AttendanceLog).where(
            AttendanceLog.tenant_container_id == company.tenant_container_id,
            AttendanceLog.company_id == company.id,
            AttendanceLog.user_id == actor.id,
            AttendanceLog.attendance_date == business_date,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AttendanceRuleError("You have already clocked in today.", 409, "already_clocked_in")
    log = AttendanceLog(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        user_id=actor.id,
        attendance_date=business_date,
        timestamp=moment,
        method=method if method != "selfie" else "selfie",
    )
    db.session.add(log)
    db.session.flush()
    if method == "selfie":
        log.selfie_data_uri, log.selfie_image_path = _store_selfie(selfie_data_uri, log_id=log.id, user_id=actor.id)
    db.session.flush()
    _audit_attendance(actor, company, action="attendance.clocked_in", entity_type="AttendanceLog", entity_id=log.id, after={"attendance_date": business_date, "method": method})
    return log


def clock_out(actor: User, *, company_id: str | None = None) -> AttendanceLog:
    company = _company_for_actor(actor, company_id)
    moment = datetime.now(timezone.utc)
    business_date = _business_date(company, moment)
    log = db.session.execute(
        select(AttendanceLog).where(
            AttendanceLog.tenant_container_id == company.tenant_container_id,
            AttendanceLog.company_id == company.id,
            AttendanceLog.user_id == actor.id,
            AttendanceLog.attendance_date == business_date,
        )
    ).scalar_one_or_none()
    if log is None:
        raise AttendanceRuleError("No clock-in record exists for today.", 409, "not_clocked_in")
    if log.clock_out_at is not None:
        raise AttendanceRuleError("You have already clocked out today.", 409, "already_clocked_out")
    log.clock_out_at = moment
    db.session.flush()
    _audit_attendance(actor, company, action="attendance.clocked_out", entity_type="AttendanceLog", entity_id=log.id, after={"clock_out_at": moment.isoformat()})
    return log


def list_attendance_logs(actor: User, *, company_id: str | None = None, business_date: str | None = None, user_id: str | None = None) -> list[AttendanceLog]:
    company = _company_for_actor(actor, company_id)
    is_admin = actor.is_admin
    statement = select(AttendanceLog).where(
        AttendanceLog.tenant_container_id == company.tenant_container_id,
        AttendanceLog.company_id == company.id,
    )
    if business_date:
        statement = statement.where(AttendanceLog.attendance_date == business_date)
    if user_id:
        if not is_admin and user_id != actor.id:
            raise AttendanceRuleError("You can only view your own attendance.", 403, "permission_denied")
        statement = statement.where(AttendanceLog.user_id == user_id)
    elif not is_admin:
        statement = statement.where(AttendanceLog.user_id == actor.id)
    statement = statement.order_by(AttendanceLog.timestamp.desc()).limit(500)
    return list(db.session.execute(statement).scalars())


def active_break(actor: User, *, company_id: str | None = None) -> BreakLog | None:
    company = _company_for_actor(actor, company_id)
    return db.session.execute(
        select(BreakLog).where(
            BreakLog.tenant_container_id == company.tenant_container_id,
            BreakLog.company_id == company.id,
            BreakLog.user_id == actor.id,
            BreakLog.is_active.is_(True),
        )
    ).scalar_one_or_none()


def _attendance_setting(company: Company) -> AttendanceSetting | None:
    return db.session.execute(
        select(AttendanceSetting).where(
            AttendanceSetting.tenant_container_id == company.tenant_container_id,
            AttendanceSetting.company_id == company.id,
        )
    ).scalar_one_or_none()


def start_break(actor: User, *, company_id: str | None = None) -> BreakLog:
    if not actor.is_authenticated:
        raise AttendanceRuleError("Sign in to start a break.", 401, "authentication_required")
    company = _company_for_actor(actor, company_id)
    setting = _attendance_setting(company)
    max_breaks = setting.max_concurrent_breaks if setting is not None else 1
    active_count = db.session.execute(
        select(func.count(BreakLog.id)).where(
            BreakLog.tenant_container_id == company.tenant_container_id,
            BreakLog.user_id == actor.id,
            BreakLog.is_active.is_(True),
        )
    ).scalar_one_or_none() or 0
    if active_count >= max_breaks:
        raise AttendanceRuleError(
            f"The concurrent break limit of {max_breaks} has been reached.",
            409,
            "break_limit_reached",
        )
    break_log = BreakLog(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        user_id=actor.id,
        start_time=datetime.now(timezone.utc),
    )
    db.session.add(break_log)
    db.session.flush()
    actor.active_break_id = break_log.id
    db.session.flush()
    _audit_attendance(actor, company, action="attendance.break_started", entity_type="BreakLog", entity_id=break_log.id, after={"start_time": break_log.start_time.isoformat()})
    return break_log


def end_break(actor: User, *, company_id: str | None = None, break_id: str | None = None) -> BreakLog:
    company = _company_for_actor(actor, company_id)
    statement = select(BreakLog).where(
        BreakLog.tenant_container_id == company.tenant_container_id,
        BreakLog.company_id == company.id,
        BreakLog.user_id == actor.id,
        BreakLog.is_active.is_(True),
    )
    if break_id:
        statement = statement.where(BreakLog.id == break_id)
    break_log = db.session.execute(statement.order_by(BreakLog.start_time.desc())).scalar_one_or_none()
    if break_log is None:
        raise AttendanceRuleError("There is no active break to end.", 409, "no_active_break")
    moment = datetime.now(timezone.utc)
    start_time = break_log.start_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    break_log.end_time = moment
    break_log.duration_ms = int((moment - start_time).total_seconds() * 1000)
    break_log.is_active = False
    if str(actor.active_break_id or "") == str(break_log.id):
        actor.active_break_id = None
    db.session.flush()
    _audit_attendance(actor, company, action="attendance.break_ended", entity_type="BreakLog", entity_id=break_log.id, after={"end_time": moment.isoformat(), "duration_ms": break_log.duration_ms})
    return break_log


def list_breaks(actor: User, *, company_id: str | None = None, user_id: str | None = None) -> list[BreakLog]:
    company = _company_for_actor(actor, company_id)
    is_admin = actor.is_admin
    statement = select(BreakLog).where(
        BreakLog.tenant_container_id == company.tenant_container_id,
        BreakLog.company_id == company.id,
    )
    if user_id:
        if not is_admin and user_id != actor.id:
            raise AttendanceRuleError("You can only view your own breaks.", 403, "permission_denied")
        statement = statement.where(BreakLog.user_id == user_id)
    elif not is_admin:
        statement = statement.where(BreakLog.user_id == actor.id)
    statement = statement.order_by(BreakLog.start_time.desc()).limit(500)
    return list(db.session.execute(statement).scalars())


def breaks_dashboard(actor: User, *, company_id: str | None = None) -> dict:
    """Active breaks and today's attendance for managers and admins."""
    company = _company_for_actor(actor, company_id)
    if not actor.is_admin and not actor.has_permission("view_reports"):
        raise AttendanceRuleError("Only managers can view the breaks dashboard.", 403, "permission_denied")
    moment = datetime.now(timezone.utc)
    business_date = _business_date(company, moment)
    active_breaks = list(
        db.session.execute(
            select(BreakLog).where(
                BreakLog.tenant_container_id == company.tenant_container_id,
                BreakLog.company_id == company.id,
                BreakLog.is_active.is_(True),
            ).order_by(BreakLog.start_time.desc())
        )
        .scalars()
    )
    today_logs = list(
        db.session.execute(
            select(AttendanceLog).where(
                AttendanceLog.tenant_container_id == company.tenant_container_id,
                AttendanceLog.company_id == company.id,
                AttendanceLog.attendance_date == business_date,
            ).order_by(AttendanceLog.timestamp.desc())
        )
        .scalars()
    )
    setting = _attendance_setting(company)
    return {
        "company_id": company.id,
        "business_date": business_date,
        "setting": (
            {
                "mandatory_attendance_time": setting.mandatory_attendance_time,
                "is_mandatory_attendance_active": setting.is_mandatory_attendance_active,
                "max_concurrent_breaks": setting.max_concurrent_breaks,
            }
            if setting
            else None
        ),
        "active_breaks": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "start_time": row.start_time.isoformat().replace("+00:00", "Z") if row.start_time else None,
            }
            for row in active_breaks
        ],
        "today_logs": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "timestamp": row.timestamp.isoformat().replace("+00:00", "Z") if row.timestamp else None,
                "method": row.method,
                "clocked_out": row.clock_out_at is not None,
            }
            for row in today_logs
        ],
    }


def get_attendance_selfie(actor: User, *, log_id: str, company_id: str | None = None) -> AttendanceLog:
    company = _company_for_actor(actor, company_id)
    log = db.session.execute(select(AttendanceLog).where(
        AttendanceLog.id == log_id,
        AttendanceLog.tenant_container_id == company.tenant_container_id,
        AttendanceLog.company_id == company.id,
    )).scalar_one_or_none()
    if log is None or not log.selfie_image_path:
        raise AttendanceRuleError("Attendance selfie not found.", 404, "not_found")
    if log.user_id != actor.id and not actor.is_admin:
        raise AttendanceRuleError("You may only view your own attendance selfie.", 403, "permission_denied")
    return log


def attendance_dict(log: AttendanceLog) -> dict:
    return {
        "id": log.id,
        "user_id": log.user_id,
        "attendance_date": log.attendance_date,
        "timestamp": log.timestamp.isoformat().replace("+00:00", "Z") if log.timestamp else None,
        "method": log.method,
        "selfie_image_path": log.selfie_image_path,
        "clock_out_at": log.clock_out_at.isoformat().replace("+00:00", "Z") if log.clock_out_at else None,
    }


def break_dict(break_log: BreakLog) -> dict:
    return {
        "id": break_log.id,
        "user_id": break_log.user_id,
        "start_time": break_log.start_time.isoformat().replace("+00:00", "Z") if break_log.start_time else None,
        "end_time": break_log.end_time.isoformat().replace("+00:00", "Z") if break_log.end_time else None,
        "duration_ms": break_log.duration_ms,
        "is_active": break_log.is_active,
    }


def new_id() -> str:
    return str(uuid4())
