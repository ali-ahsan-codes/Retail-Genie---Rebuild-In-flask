"""Settings pages and JSON APIs for company-scoped configuration."""

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from ..auth.tenant_context import current_membership, current_tenant_container_id, select_container_for_session
from ..extensions import db
from ..models import (
    BillingSeries,
    BusinessNumberSeries,
    Company,
    OrderNumberSeries,
)
from . import settings_bp
from .service import (
    SettingsRuleError,
    company_today,
    effective_global_discount_percentage,
    get_attendance_setting,
    get_commission_setting,
    list_global_discounts,
    list_tax_settings,
    settings_summary,
    update_attendance_settings,
    update_commission_settings,
    update_global_discount_settings,
    update_tax_settings,
)


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict(flat=True)


def _error(error: SettingsRuleError):
    return jsonify(error=error.code, message=str(error)), error.status_code


def _resolve_company():
    """Resolve the company the acting user may administer settings for."""
    if current_user.is_super_admin:
        company_id = request.args.get("company_id") or request.form.get("company_id")
        if company_id:
            company = db.session.get(Company, company_id)
            if company is None or not company.is_active:
                return None, []
            active_container_id = current_tenant_container_id(current_user)
            if active_container_id != company.tenant_container_id:
                if not select_container_for_session(current_user, company.tenant_container_id):
                    return None, []
            companies = list(
                db.session.execute(
                    select(Company)
                    .where(Company.tenant_container_id == company.tenant_container_id, Company.is_active.is_(True))
                    .order_by(Company.name.asc())
                )
                .scalars()
            )
            return company, companies
        companies = list(
            db.session.execute(
                select(Company).where(Company.is_active.is_(True)).order_by(Company.name.asc())
            ).scalars()
        )
        return None, companies
    membership = current_membership(current_user)
    if membership is None or not membership.company_id:
        return None, []
    company = db.session.get(Company, membership.company_id)
    if company is None or not company.is_active:
        return None, []
    return company, []


def _require_company_admin() -> None:
    if not current_user.is_authenticated or not (current_user.is_admin or current_user.has_permission("manage_settings")):
        abort(403)


@settings_bp.get("/settings")
@login_required
def settings_index():
    _require_company_admin()
    company, companies = _resolve_company()
    if company is None:
        return render_template("settings/index.html", company=None, companies=companies, summary=None, series=[])
    summary = settings_summary(current_user, company.id)
    series = _series_rows(company)
    effective_discount = effective_global_discount_percentage(company)
    return render_template(
        "settings/index.html",
        company=company,
        companies=companies,
        summary=summary,
        series=series,
        today=company_today(company),
        effective_discount=effective_discount,
    )


def _series_rows(company: Company) -> list[dict]:
    """Billing, order, and commercial document counters for one company."""
    rows: list[dict] = []
    for series in db.session.execute(
        select(BillingSeries)
        .where(BillingSeries.tenant_container_id == company.tenant_container_id, BillingSeries.company_id == company.id)
        .order_by(BillingSeries.category.asc())
    ).scalars():
        rows.append(
            {
                "kind": "invoice",
                "document_type": series.category,
                "label": f"{series.category.replace('_', ' ').title()} invoice",
                "prefix": series.prefix,
                "next_number": series.next_number,
                "id": series.id,
            }
        )
    order_series = db.session.execute(
        select(OrderNumberSeries).where(
            OrderNumberSeries.tenant_container_id == company.tenant_container_id,
            OrderNumberSeries.company_id == company.id,
        )
    ).scalar_one_or_none()
    if order_series is not None:
        rows.append(
            {
                "kind": "order",
                "document_type": "order",
                "label": "Order reference",
                "prefix": order_series.prefix,
                "next_number": order_series.next_number,
                "id": order_series.id,
            }
        )
    for series in db.session.execute(
        select(BusinessNumberSeries)
        .where(
            BusinessNumberSeries.tenant_container_id == company.tenant_container_id,
            BusinessNumberSeries.company_id == company.id,
        )
        .order_by(BusinessNumberSeries.document_type.asc())
    ).scalars():
        rows.append(
            {
                "kind": "commercial",
                "document_type": series.document_type,
                "label": series.document_type.replace("_", " ").title(),
                "prefix": series.prefix,
                "next_number": series.next_number,
                "id": series.id,
            }
        )
    return rows


@settings_bp.post("/api/v1/settings/tax")
@login_required
def update_tax():
    _require_company_admin()
    data = _payload()
    try:
        taxes = update_tax_settings(current_user, data.get("company_id"), taxes=data.get("taxes", []))
        db.session.commit()
    except SettingsRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify(
        {
            "taxes": [
                {"id": tax.id, "name": tax.name, "rate": str(tax.rate), "is_enabled": tax.is_enabled}
                for tax in taxes
            ]
        }
    ), 200


@settings_bp.post("/api/v1/settings/commission")
@login_required
def update_commission():
    _require_company_admin()
    data = _payload()
    try:
        setting = update_commission_settings(
            current_user,
            data.get("company_id"),
            sales_target=data.get("sales_target", 0),
            commission_interval=str(data.get("commission_interval", "monthly")),
            commission_percentage=data.get("commission_percentage", 0),
            is_active=data.get("is_active", False),
        )
        db.session.commit()
    except SettingsRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify(
        {
            "id": setting.id,
            "sales_target": str(setting.sales_target),
            "commission_interval": setting.commission_interval,
            "commission_percentage": str(setting.commission_percentage),
            "is_active": setting.is_active,
        }
    ), 200


@settings_bp.post("/api/v1/settings/global-discount")
@login_required
def update_global_discount():
    _require_company_admin()
    data = _payload()
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    try:
        from datetime import date as _date

        start = _date.fromisoformat(str(start_date)) if start_date else None
        end = _date.fromisoformat(str(end_date)) if end_date else None
        setting = update_global_discount_settings(
            current_user,
            data.get("company_id"),
            percentage=data.get("percentage", 0),
            start_date=start,
            end_date=end,
            is_active=data.get("is_active", False),
            description=data.get("description"),
        )
        db.session.commit()
    except (SettingsRuleError, ValueError) as error:
        db.session.rollback()
        if isinstance(error, SettingsRuleError):
            return _error(error)
        return _error(SettingsRuleError("Dates must use YYYY-MM-DD format."))
    return jsonify(
        {
            "id": setting.id,
            "percentage": str(setting.percentage),
            "start_date": setting.start_date.isoformat() if setting.start_date else None,
            "end_date": setting.end_date.isoformat() if setting.end_date else None,
            "is_active": setting.is_active,
            "description": setting.description,
        }
    ), 200


@settings_bp.post("/api/v1/settings/attendance")
@login_required
def update_attendance():
    _require_company_admin()
    data = _payload()
    try:
        setting = update_attendance_settings(
            current_user,
            data.get("company_id"),
            mandatory_attendance_time=(data.get("mandatory_attendance_time") or None),
            is_mandatory_attendance_active=data.get("is_mandatory_attendance_active", False),
            max_concurrent_breaks=int(data.get("max_concurrent_breaks", 1)),
        )
        db.session.commit()
    except (SettingsRuleError, ValueError, TypeError) as error:
        db.session.rollback()
        if isinstance(error, SettingsRuleError):
            return _error(error)
        return _error(SettingsRuleError("Maximum concurrent breaks must be a whole number."))
    return jsonify(
        {
            "id": setting.id,
            "mandatory_attendance_time": setting.mandatory_attendance_time,
            "is_mandatory_attendance_active": setting.is_mandatory_attendance_active,
            "max_concurrent_breaks": setting.max_concurrent_breaks,
        }
    ), 200


@settings_bp.post("/api/v1/settings/series/<string:series_id>/next-number")
@login_required
def update_series_next_number(series_id: str):
    """Move a document counter forward; every change is audited."""
    _require_company_admin()
    data = _payload()
    try:
        next_number = int(data.get("next_number", 0))
    except (TypeError, ValueError):
        return _error(SettingsRuleError("The next number must be a whole number."))
    if next_number < 1:
        return _error(SettingsRuleError("The next number must be at least 1."))
    company, _ = _resolve_company()
    if company is None:
        return _error(SettingsRuleError("Company not found.", 404, "not_found"))
    try:
        result = _advance_series(current_user, company, series_id, next_number)
    except SettingsRuleError as error:
        db.session.rollback()
        return _error(error)
    db.session.commit()
    return jsonify(result), 200


def _advance_series(actor, company: Company, series_id: str, next_number: int) -> dict:
    from ..models import AuditEvent

    queries = [
        (BillingSeries, "invoice"),
        (OrderNumberSeries, "order"),
        (BusinessNumberSeries, "commercial"),
    ]
    for model, kind in queries:
        series = db.session.execute(
            select(model).where(
                model.id == series_id,
                model.tenant_container_id == company.tenant_container_id,
                model.company_id == company.id,
            )
        ).scalar_one_or_none()
        if series is None:
            continue
        before = {"next_number": series.next_number}
        series.next_number = next_number
        db.session.flush()
        document_type = series.category if kind == "invoice" else (series.document_type if kind == "commercial" else "order")
        db.session.add(
            AuditEvent(
                tenant_container_id=company.tenant_container_id,
                company_id=company.id,
                actor_user_id=actor.id,
                action="settings.series.updated",
                entity_type=model.__name__,
                entity_id=series.id,
                before_data=before,
                after_data={"next_number": next_number, "document_type": document_type},
            )
        )
        return {"kind": kind, "document_type": document_type, "prefix": series.prefix, "next_number": next_number}
    raise SettingsRuleError("Numbering series not found.", 404, "not_found")


@settings_bp.get("/api/v1/settings/summary")
@login_required
def settings_summary_api():
    company, _ = _resolve_company()
    if company is None:
        return jsonify(error="not_found"), 404
    try:
        summary = settings_summary(current_user, company.id)
        summary["effective_global_discount_percentage"] = str(
            effective_global_discount_percentage(company)
        )
    except SettingsRuleError as error:
        return _error(error)
    return jsonify(summary), 200
