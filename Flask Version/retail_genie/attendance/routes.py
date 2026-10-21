"""Attendance and break pages and JSON APIs."""

from pathlib import Path

from flask import abort, current_app, jsonify, render_template, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import select

from ..extensions import db
from ..models import Company
from . import attendance_bp
from .service import (
    AttendanceRuleError,
    attendance_dict,
    breaks_dashboard,
    break_dict,
    clock_in,
    clock_out,
    get_attendance_selfie,
    end_break,
    list_attendance_logs,
    list_breaks,
    start_break,
)


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict(flat=True)


def _error(error: AttendanceRuleError):
    return jsonify(error=error.code, message=str(error)), error.status_code


def _company_id() -> str | None:
    data = _payload()
    return data.get("company_id") or request.args.get("company_id")


@attendance_bp.get("/attendance")
@login_required
def attendance_page():
    company_id = _company_id()
    company = None
    if current_user.is_super_admin:
        company = db.session.get(Company, company_id) if company_id else None
    else:
        from ..auth.tenant_context import current_membership

        membership = current_membership(current_user)
        if membership is not None and membership.company_id:
            company = db.session.get(Company, membership.company_id)
    if company is None:
        return render_template("attendance/index.html", company=None, logs=[], breaks=[])
    try:
        logs = [attendance_dict(log) for log in list_attendance_logs(current_user, company_id=company.id)]
        breaks = [break_dict(row) for row in list_breaks(current_user, company_id=company.id)]
    except AttendanceRuleError as error:
        abort(error.status_code)
    return render_template("attendance/index.html", company=company, logs=logs, breaks=breaks)


@attendance_bp.post("/api/v1/attendance/clock-in")
@login_required
def clock_in_api():
    data = _payload()
    try:
        log = clock_in(
            current_user,
            company_id=data.get("company_id"),
            method=str(data.get("method", "auto")),
            selfie_data_uri=data.get("selfie_data_uri"),
        )
        db.session.commit()
    except AttendanceRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"attendance": attendance_dict(log)}), 201


@attendance_bp.get("/api/v1/attendance/logs/<string:log_id>/selfie")
@login_required
def attendance_selfie_api(log_id: str):
    try:
        log = get_attendance_selfie(current_user, log_id=log_id, company_id=request.args.get("company_id"))
    except AttendanceRuleError as error:
        return _error(error)
    root = Path(current_app.config["UPLOADS_DIR"]).resolve()
    path = (root / log.selfie_image_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    response = send_file(path, as_attachment=False, conditional=True, download_name=path.name)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@attendance_bp.post("/api/v1/attendance/clock-out")
@login_required
def clock_out_api():
    data = _payload()
    try:
        log = clock_out(current_user, company_id=data.get("company_id"))
        db.session.commit()
    except AttendanceRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"attendance": attendance_dict(log)}), 200


@attendance_bp.get("/api/v1/attendance/logs")
@login_required
def attendance_logs_api():
    try:
        logs = list_attendance_logs(
            current_user,
            company_id=_company_id(),
            business_date=request.args.get("date"),
            user_id=request.args.get("user_id"),
        )
    except AttendanceRuleError as error:
        return _error(error)
    return jsonify({"logs": [attendance_dict(log) for log in logs]}), 200


@attendance_bp.post("/api/v1/breaks")
@login_required
def start_break_api():
    data = _payload()
    try:
        break_log = start_break(current_user, company_id=data.get("company_id"))
        db.session.commit()
    except AttendanceRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"break": break_dict(break_log)}), 201


@attendance_bp.post("/api/v1/breaks/<string:break_id>/end")
@login_required
def end_break_api(break_id: str):
    data = _payload()
    try:
        break_log = end_break(current_user, company_id=data.get("company_id"), break_id=break_id or None)
        db.session.commit()
    except AttendanceRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"break": break_dict(break_log)}), 200


@attendance_bp.get("/api/v1/breaks")
@login_required
def breaks_api():
    try:
        rows = list_breaks(current_user, company_id=_company_id(), user_id=request.args.get("user_id"))
    except AttendanceRuleError as error:
        return _error(error)
    return jsonify({"breaks": [break_dict(row) for row in rows]}), 200


@attendance_bp.get("/admin/breaks-dashboard")
@login_required
def breaks_dashboard_page():
    try:
        dashboard = breaks_dashboard(current_user, company_id=_company_id())
    except AttendanceRuleError as error:
        abort(error.status_code)
    return render_template("attendance/breaks_dashboard.html", dashboard=dashboard)
