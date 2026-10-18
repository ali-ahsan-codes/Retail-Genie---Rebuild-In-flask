"""Flask APIs and server-rendered pages for commercial workflows."""

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import CatalogProduct, Company, Store
from ..sales.service import SalesRuleError, order_dict
from . import commercial_bp
from .service import (
    cancel_demand_notice,
    change_quotation_status,
    convert_demand_notice_to_order,
    convert_quotation_to_order,
    create_demand_notice,
    create_quotation,
    demand_notice_dict,
    list_demand_notices,
    list_quotations,
    quotation_dict,
)


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict(flat=True)


def _error(error: SalesRuleError):
    return jsonify(error=error.code, message=str(error)), error.status_code


def _page_context(template: str):
    companies = Company.query.filter_by(is_active=True).order_by(Company.name.asc()).all() if current_user.is_super_admin else []
    company_id = request.args.get("company_id") or request.form.get("company_id")
    if current_user.is_super_admin:
        company = db.session.get(Company, company_id) if company_id else None
        if company is not None and not company.is_active:
            company = None
    else:
        membership = current_membership(current_user)
        company = db.session.get(Company, membership.company_id) if membership and membership.company_id else None
    if current_user.is_super_admin and company is None:
        return render_template(template, company=None, companies=companies, stores=[], records=[], products=[])
    if company is None or not company.is_active:
        abort(404)
    allowed = accessible_store_ids(current_user, company_id=company.id, tenant_container_id=company.tenant_container_id)
    stores = Store.query.filter(Store.id.in_(allowed), Store.is_active.is_(True)).order_by(Store.code.asc()).all() if allowed else []
    store_id = request.args.get("store_id") or request.form.get("store_id")
    if store_id and store_id not in allowed:
        abort(404)
    if store_id and not can_access_data_domain(
        current_user,
        tenant_container_id=company.tenant_container_id,
        domain="sales",
        action="view",
        company_id=company.id,
        store_id=store_id,
    ):
        abort(403)
    products = []
    if store_id and can_access_data_domain(
        current_user,
        tenant_container_id=company.tenant_container_id,
        domain="product_catalog",
        action="view",
        company_id=company.id,
        store_id=store_id,
    ):
        products = db.session.execute(
            select(CatalogProduct)
            .where(
                CatalogProduct.tenant_container_id == company.tenant_container_id,
                CatalogProduct.company_id == company.id,
                CatalogProduct.is_active.is_(True),
            )
            .order_by(CatalogProduct.name.asc())
            .limit(500)
        ).scalars().all()
    records = []
    if store_id:
        try:
            if template.endswith("demand_notices.html"):
                records = list_demand_notices(current_user, company_id=company.id, store_id=store_id)
            else:
                records = list_quotations(current_user, company_id=company.id, store_id=store_id)
        except SalesRuleError as error:
            if error.status_code not in {403}:
                raise
    return render_template(
        template,
        company=company,
        companies=companies,
        stores=stores,
        selected_store_id=store_id,
        records=records,
        products=products,
    )


@commercial_bp.get("/demand-notices")
@login_required
def demand_notices_page():
    return _page_context("commercial/demand_notices.html")


@commercial_bp.post("/demand-notices")
@login_required
def create_demand_notice_page():
    data = _payload()
    try:
        notice = create_demand_notice(
            current_user,
            company_id=data.get("company_id"),
            store_id=str(data.get("store_id", "")),
            customer_phone=data.get("customer_phone", ""),
            customer_name=data.get("customer_name"),
            product_id=data.get("product_id") or None,
            product_name=data.get("product_name"),
            product_sku=data.get("product_sku"),
            quantity_requested=data.get("quantity_requested"),
            agreed_price=data.get("agreed_price"),
            expected_availability_date=data.get("expected_availability_date"),
            is_new_product=data.get("is_new_product") or None,
            notes=data.get("notes"),
        )
        flash(f"Demand notice {notice.notice_number} created.", "success")
    except SalesRuleError as error:
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("The demand notice conflicted with existing data and was not saved.", "error")
    return redirect(url_for("commercial.demand_notices_page", company_id=data.get("company_id"), store_id=data.get("store_id")))


@commercial_bp.get("/quotations")
@login_required
def quotations_page():
    return _page_context("commercial/quotations.html")


@commercial_bp.post("/quotations")
@login_required
def create_quotation_page():
    data = _payload()
    try:
        line = {
            "product_id": data.get("product_id"),
            "product_name": data.get("product_name"),
            "product_sku": data.get("product_sku"),
            "quantity": data.get("quantity"),
            "unit_price": data.get("unit_price"),
            "is_external": data.get("is_external", "false"),
        }
        quotation = create_quotation(
            current_user,
            company_id=data.get("company_id"),
            store_id=str(data.get("store_id", "")),
            customer_phone=data.get("customer_phone", ""),
            customer_name=data.get("customer_name"),
            customer_email=data.get("customer_email"),
            customer_address=data.get("customer_address"),
            preparation_days=data.get("preparation_days", 0),
            valid_until=data.get("valid_until"),
            notes=data.get("notes"),
            lines=[line],
        )
        flash(f"Quotation {quotation.quotation_number} created as a draft.", "success")
    except SalesRuleError as error:
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("The quotation conflicted with existing data and was not saved.", "error")
    return redirect(url_for("commercial.quotations_page", company_id=data.get("company_id"), store_id=data.get("store_id")))


@commercial_bp.get("/api/v1/demand-notices")
@login_required
def api_list_demand_notices():
    try:
        rows = list_demand_notices(
            current_user,
            company_id=request.args.get("company_id"),
            store_id=request.args.get("store_id"),
            status=request.args.get("status"),
            search=request.args.get("q"),
        )
        return jsonify(demand_notices=rows)
    except SalesRuleError as error:
        return _error(error)


@commercial_bp.post("/api/v1/demand-notices")
@login_required
def api_create_demand_notice():
    data = _payload()
    try:
        notice = create_demand_notice(
            current_user,
            company_id=data.get("company_id"),
            store_id=str(data.get("store_id", "")),
            customer_phone=data.get("customer_phone", ""),
            customer_name=data.get("customer_name"),
            product_id=data.get("product_id"),
            product_name=data.get("product_name"),
            product_sku=data.get("product_sku"),
            quantity_requested=data.get("quantity_requested"),
            agreed_price=data.get("agreed_price"),
            expected_availability_date=data.get("expected_availability_date"),
            is_new_product=data.get("is_new_product"),
            notes=data.get("notes"),
        )
        return jsonify(demand_notice=demand_notice_dict(notice)), 201
    except SalesRuleError as error:
        return _error(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The demand notice conflicted with existing data."), 409


@commercial_bp.post("/api/v1/demand-notices/<string:notice_id>/cancel")
@login_required
def api_cancel_demand_notice(notice_id: str):
    data = _payload()
    try:
        notice = cancel_demand_notice(
            current_user,
            notice_id=notice_id,
            company_id=data.get("company_id"),
            reason=data.get("reason", ""),
        )
        return jsonify(demand_notice=demand_notice_dict(notice))
    except SalesRuleError as error:
        return _error(error)


@commercial_bp.post("/api/v1/demand-notices/<string:notice_id>/convert")
@login_required
def api_convert_demand_notice(notice_id: str):
    data = _payload()
    try:
        order, replayed = convert_demand_notice_to_order(
            current_user,
            notice_id=notice_id,
            company_id=data.get("company_id"),
        )
        return jsonify(order=order_dict(order), replayed=replayed), (200 if replayed else 201)
    except SalesRuleError as error:
        return _error(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The notice conversion conflicted; retry safely."), 409


@commercial_bp.get("/api/v1/quotations")
@login_required
def api_list_quotations():
    try:
        rows = list_quotations(
            current_user,
            company_id=request.args.get("company_id"),
            store_id=request.args.get("store_id"),
            status=request.args.get("status"),
            search=request.args.get("q"),
        )
        return jsonify(quotations=rows)
    except SalesRuleError as error:
        return _error(error)


@commercial_bp.post("/api/v1/quotations")
@login_required
def api_create_quotation():
    data = _payload()
    try:
        quotation = create_quotation(
            current_user,
            company_id=data.get("company_id"),
            store_id=str(data.get("store_id", "")),
            customer_phone=data.get("customer_phone", ""),
            customer_name=data.get("customer_name"),
            customer_email=data.get("customer_email"),
            customer_address=data.get("customer_address"),
            preparation_days=data.get("preparation_days", 0),
            valid_until=data.get("valid_until"),
            notes=data.get("notes"),
            lines=data.get("lines"),
        )
        return jsonify(quotation=quotation_dict(quotation)), 201
    except SalesRuleError as error:
        return _error(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The quotation conflicted with existing data."), 409


@commercial_bp.post("/api/v1/quotations/<string:quotation_id>/status")
@login_required
def api_change_quotation_status(quotation_id: str):
    data = _payload()
    try:
        quotation = change_quotation_status(
            current_user,
            quotation_id=quotation_id,
            status=str(data.get("status", "")),
            company_id=data.get("company_id"),
        )
        return jsonify(quotation=quotation_dict(quotation))
    except SalesRuleError as error:
        return _error(error)


@commercial_bp.post("/api/v1/quotations/<string:quotation_id>/convert")
@login_required
def api_convert_quotation(quotation_id: str):
    data = _payload()
    try:
        order, replayed = convert_quotation_to_order(
            current_user,
            quotation_id=quotation_id,
            company_id=data.get("company_id"),
        )
        return jsonify(order=order_dict(order), replayed=replayed), (200 if replayed else 201)
    except SalesRuleError as error:
        return _error(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The quotation conversion conflicted; retry safely."), 409
