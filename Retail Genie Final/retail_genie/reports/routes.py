"""Sales, activity-log, and salesperson reporting pages/APIs."""

from datetime import date

from flask import abort, jsonify, make_response, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership
from ..extensions import db
from ..models import Company, Store
from . import reports_bp
from .service import ReportRuleError, activity_log, report_csv, sales_report


def _scope_context():
    if current_user.is_super_admin:
        company_id = request.args.get("company_id")
        company = db.session.get(Company, company_id) if company_id else None
        if company is None or not company.is_active:
            return None, [], []
    else:
        membership = current_membership(current_user)
        company = db.session.get(Company, membership.company_id) if membership and membership.company_id else None
        if company is None or not company.is_active:
            return None, [], []
    ids = accessible_store_ids(current_user, company_id=company.id, tenant_container_id=company.tenant_container_id)
    stores = list(db.session.execute(select(Store).where(Store.id.in_(ids), Store.is_active.is_(True)).order_by(Store.code)).scalars()) if ids else []
    return company, stores, [company] if current_user.is_super_admin else []


def _date_arg(key: str):
    value = request.args.get(key)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ReportRuleError(f"{key.replace('_', ' ').title()} must use YYYY-MM-DD format.") from None


def _error(error: ReportRuleError):
    return jsonify(error=error.code, message=str(error)), error.status_code


@reports_bp.get("/admin/salesperson-reports")
@login_required
def salesperson_reports_page():
    company, stores, companies = _scope_context()
    if company is None:
        return render_template("reports/sales.html", company=None, stores=[], report=None)
    if not (current_user.is_admin or current_user.has_permission("view_salesperson_reports") or current_user.has_permission("view_reports")):
        abort(403)
    try:
        report = sales_report(
            current_user,
            company_id=company.id,
            store_id=request.args.get("store_id") or None,
            start_date=_date_arg("start_date"),
            end_date=_date_arg("end_date"),
            salesperson_id=request.args.get("salesperson_id") or None,
        )
    except ReportRuleError as error:
        abort(error.status_code)
    return render_template("reports/sales.html", company=company, stores=stores, report=report)


@reports_bp.get("/admin/activity-logs")
@login_required
def activity_logs_page():
    company, stores, _companies = _scope_context()
    if company is None:
        return render_template("reports/activity.html", company=None, stores=[], events=[])
    try:
        events = activity_log(
            current_user,
            company_id=company.id,
            store_id=request.args.get("store_id") or None,
            limit=request.args.get("limit", 200, type=int),
        )
    except ReportRuleError as error:
        abort(error.status_code)
    return render_template("reports/activity.html", company=company, stores=stores, events=events)


@reports_bp.get("/api/v1/reports/sales")
@login_required
def sales_report_api():
    company_id = request.args.get("company_id")
    try:
        report = sales_report(
            current_user,
            company_id=company_id,
            store_id=request.args.get("store_id") or None,
            start_date=_date_arg("start_date"),
            end_date=_date_arg("end_date"),
            salesperson_id=request.args.get("salesperson_id") or None,
        )
    except ReportRuleError as error:
        return _error(error)
    return jsonify(report), 200


@reports_bp.get("/api/v1/reports/sales.csv")
@login_required
def sales_report_csv():
    try:
        report = sales_report(
            current_user,
            company_id=request.args.get("company_id"),
            store_id=request.args.get("store_id") or None,
            start_date=_date_arg("start_date"),
            end_date=_date_arg("end_date"),
            salesperson_id=request.args.get("salesperson_id") or None,
        )
    except ReportRuleError as error:
        return _error(error)
    response = make_response(report_csv(report))
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=retail-genie-sales-report.csv"
    return response


@reports_bp.get("/api/v1/reports/activity")
@login_required
def activity_api():
    try:
        events = activity_log(
            current_user,
            company_id=request.args.get("company_id"),
            store_id=request.args.get("store_id") or None,
            limit=request.args.get("limit", 200, type=int),
        )
    except ReportRuleError as error:
        return _error(error)
    return jsonify({"events": events}), 200
