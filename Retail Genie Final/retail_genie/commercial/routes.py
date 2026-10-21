"""Flask APIs and server-rendered pages for commercial workflows."""

import re
from html import escape

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import CatalogProduct, Company, Store
from ..sales.service import SalesRuleError, _add_audit, order_dict
from .emailing import CommercialEmailError, send_commercial_email
from . import commercial_bp
from .service import (
    cancel_demand_notice,
    change_quotation_status,
    convert_demand_notice_to_order,
    convert_quotation_to_order,
    fulfill_demand_notice,
    create_demand_notice,
    create_quotation,
    demand_notice_dict,
    list_demand_notices,
    list_quotations,
    quotation_dict,
    get_demand_notice_document,
    get_quotation_document,
    record_demand_notice_payment,
    update_demand_notice,
    update_quotation,
)


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict(flat=True)


def _error(error: SalesRuleError):
    db.session.rollback()
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


@commercial_bp.post("/api/v1/demand-notices/<string:notice_id>/fulfill")
@login_required
def api_fulfill_demand_notice(notice_id: str):
    data = _payload()
    try:
        order, replayed = fulfill_demand_notice(
            current_user,
            notice_id=notice_id,
            company_id=data.get("company_id"),
            quantity=data.get("quantity"),
            idempotency_key=data.get("idempotency_key") or request.headers.get("Idempotency-Key", ""),
        )
        return jsonify(order=order_dict(order), replayed=replayed), (200 if replayed else 201)
    except SalesRuleError as error:
        return _error(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The fulfillment conflicted; retry using the same idempotency key."), 409


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


@commercial_bp.patch("/api/v1/demand-notices/<string:notice_id>")
@login_required
def api_update_demand_notice(notice_id: str):
    data = _payload()
    try:
        notice = update_demand_notice(current_user, notice_id=notice_id, data=data, company_id=data.get("company_id"))
        return jsonify(demand_notice=demand_notice_dict(notice))
    except SalesRuleError as error:
        return _error(error)


@commercial_bp.post("/api/v1/demand-notices/<string:notice_id>/payments")
@login_required
def api_record_demand_notice_payment(notice_id: str):
    data = _payload()
    try:
        notice, replayed = record_demand_notice_payment(
            current_user,
            notice_id=notice_id,
            company_id=data.get("company_id"),
            amount=data.get("amount"),
            method=data.get("method", ""),
            reference=data.get("reference"),
            idempotency_key=data.get("idempotency_key") or request.headers.get("Idempotency-Key", ""),
        )
        return jsonify(demand_notice=demand_notice_dict(notice), replayed=replayed), (200 if replayed else 201)
    except SalesRuleError as error:
        return _error(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The payment conflicted with existing data; retry with the same key."), 409


@commercial_bp.patch("/api/v1/quotations/<string:quotation_id>")
@login_required
def api_update_quotation(quotation_id: str):
    data = _payload()
    try:
        quotation = update_quotation(current_user, quotation_id=quotation_id, data=data, company_id=data.get("company_id"))
        return jsonify(quotation=quotation_dict(quotation))
    except SalesRuleError as error:
        return _error(error)


@commercial_bp.get("/commercial/demand-notices/<string:notice_id>/print")
@login_required
def print_demand_notice(notice_id: str):
    try:
        notice = get_demand_notice_document(current_user, notice_id=notice_id, company_id=request.args.get("company_id"))
        return render_template("commercial/demand_notice_print.html", document=notice, company_id=request.args.get("company_id"))
    except SalesRuleError as error:
        return _error(error)


@commercial_bp.get("/commercial/quotations/<string:quotation_id>/print")
@login_required
def print_quotation(quotation_id: str):
    try:
        quotation = get_quotation_document(current_user, quotation_id=quotation_id, company_id=request.args.get("company_id"))
        return render_template("commercial/quotation_print.html", document=quotation, company_id=request.args.get("company_id"))
    except SalesRuleError as error:
        return _error(error)


def _email_document(kind: str, document_id: str):
    data = _payload()
    company_id = data.get("company_id")
    try:
        if kind == "quotation":
            document = get_quotation_document(current_user, quotation_id=document_id, company_id=company_id)
            reference = document["quotation_number"]
            entity_type = "quotation"
            action = "commercial.quotation.emailed"
        else:
            document = get_demand_notice_document(current_user, notice_id=document_id, company_id=company_id)
            reference = document["notice_number"]
            entity_type = "demand_notice"
            action = "commercial.demand_notice.emailed"
    except SalesRuleError as error:
        return _error(error)

    can_edit_domain = can_access_data_domain(
        current_user,
        tenant_container_id=document["tenant_container_id"],
        domain="sales",
        action="edit",
        company_id=document["company_id"],
        store_id=document["store_id"],
    )
    if not can_edit_domain or not (current_user.is_admin or current_user.has_permission("sales.edit")):
        return jsonify(error="permission_denied", message="You are not allowed to email this commercial document."), 403

    recipient = str(data.get("recipient", document.get("customer_email") or "")).strip()
    if len(recipient) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]{2,}", recipient):
        return jsonify(error="invalid_email", message="Enter a valid recipient email address."), 400

    rows = []
    if kind == "quotation":
        rows.extend(
            f"<tr><td>{escape(str(line.get('product_name') or 'Item'))}</td>"
            f"<td>{escape(str(line.get('quantity', '')))}</td>"
            f"<td>{escape(str(line.get('unit_price', '')))}</td>"
            f"<td>{escape(str(line.get('line_total', '')))}</td></tr>"
            for line in document.get("lines", [])
        )
        heading = "Quotation"
        details = f"<p>Valid until: {escape(str(document.get('valid_until') or '—'))}</p><p>Total OMR: {escape(str(document.get('total_amount') or '0.000'))}</p>"
        table = "<table><thead><tr><th>Item</th><th>Quantity</th><th>Unit price (OMR)</th><th>Line total (OMR)</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    else:
        heading = "Demand notice"
        details = (
            f"<p>Product: {escape(str(document.get('product_name') or '—'))}</p>"
            f"<p>Quantity requested: {escape(str(document.get('quantity_requested') or 0))}; fulfilled: {escape(str(document.get('quantity_fulfilled') or 0))}</p>"
            f"<p>Agreed unit price (OMR): {escape(str(document.get('agreed_price') or '—'))}</p>"
            f"<p>Deposit paid (OMR): {escape(str(document.get('amount_paid') or '0.000'))}</p>"
        )
        table = ""
    customer = escape(str(document.get("customer_name") or "Customer"))
    notes = f"<p>Notes: {escape(str(document['notes']))}</p>" if document.get("notes") else ""
    html_body = (
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>body{font:16px Arial,sans-serif;color:#172033}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3dd;padding:8px;text-align:left}</style></head><body>"
        f"<h1>Retail Genie · {heading} {escape(str(reference))}</h1><p>Customer: {customer}</p>"
        f"<p>Phone: {escape(str(document.get('customer_phone') or '—'))}</p>{details}{table}{notes}</body></html>"
    )
    try:
        send_commercial_email(recipient=recipient, subject=f"{heading} {reference}", html_body=html_body)
    except CommercialEmailError as error:
        current_app.logger.warning("Commercial document email failed for %s: %s", entity_type, error)
        return jsonify(error="email_delivery_failed", message=str(error)), 503

    company = db.session.get(Company, document["company_id"])
    _add_audit(
        company.id,
        current_user.id,
        action,
        entity_type,
        document_id,
        store_id=document["store_id"],
        after={"recipient": recipient},
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Commercial document email audit could not be committed")
        return jsonify(error="audit_write_failed", message="The email was sent, but its audit record could not be saved. Contact an administrator."), 500
    return jsonify(status="sent", document_number=reference, recipient=recipient), 201


@commercial_bp.post("/api/v1/demand-notices/<string:notice_id>/email")
@login_required
def email_demand_notice(notice_id: str):
    return _email_document("demand_notice", notice_id)


@commercial_bp.post("/api/v1/quotations/<string:quotation_id>/email")
@login_required
def email_quotation(quotation_id: str):
    return _email_document("quotation", quotation_id)
