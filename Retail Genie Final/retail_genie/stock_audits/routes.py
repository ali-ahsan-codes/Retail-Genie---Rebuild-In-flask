"""Stock audit pages and JSON APIs."""

from flask import abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from ..extensions import db
from ..models import Company, Store
from . import stock_audits_bp
from .service import (
    StockAuditRuleError,
    add_count_evidence,
    audit_counts,
    audit_dict,
    audit_evidence,
    cancel_stock_audit,
    complete_stock_audit,
    create_stock_audit,
    list_stock_audits,
    record_count,
    start_stock_audit,
)


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict(flat=True)


def _error(error: StockAuditRuleError):
    return jsonify(error=error.code, message=str(error)), error.status_code


def _resolve_company():
    if current_user.is_super_admin:
        company_id = request.args.get("company_id") or request.form.get("company_id")
        company = db.session.get(Company, company_id) if company_id else None
        if company is None or not company.is_active:
            return None
    else:
        from ..auth.tenant_context import current_membership

        membership = current_membership(current_user)
        company = db.session.get(Company, membership.company_id) if membership and membership.company_id else None
    if company is None or not company.is_active:
        return None
    return company


@stock_audits_bp.get("/audits")
@login_required
def audits_page():
    company = _resolve_company()
    if company is None:
        return render_template("stock_audits/index.html", company=None, companies=[], audits=[])
    try:
        audits = list_stock_audits(current_user, company_id=company.id)
    except StockAuditRuleError as error:
        abort(error.status_code)
    return render_template("stock_audits/index.html", company=company, companies=[], audits=audits)


@stock_audits_bp.get("/audits/create")
@login_required
def create_audit_page():
    company = _resolve_company()
    if company is None:
        abort(404)
    stores = []
    from ..auth.store_scope import accessible_store_ids

    allowed = accessible_store_ids(current_user, company_id=company.id, tenant_container_id=company.tenant_container_id)
    if allowed:
        stores = list(db.session.execute(select(Store).where(Store.id.in_(allowed), Store.is_active.is_(True))).scalars())
    products = []
    from ..models import CatalogProduct

    products = list(
        db.session.execute(
            select(CatalogProduct).where(
                CatalogProduct.tenant_container_id == company.tenant_container_id,
                CatalogProduct.company_id == company.id,
                CatalogProduct.is_active.is_(True),
            ).order_by(CatalogProduct.name.asc()).limit(1000)
        ).scalars()
    )
    return render_template("stock_audits/create.html", company=company, stores=stores, products=products)


@stock_audits_bp.post("/api/v1/audits")
@login_required
def create_audit_api():
    data = _payload()
    product_ids = data.get("product_ids") or []
    if isinstance(product_ids, str):
        product_ids = [product_ids]
    try:
        audit = create_stock_audit(
            current_user,
            company_id=data.get("company_id"),
            store_id=str(data.get("store_id", "")),
            title=data.get("title"),
            product_ids=[str(value) for value in product_ids],
            store_location=data.get("store_location"),
            auditor_id=data.get("auditor_id") or None,
        )
        db.session.commit()
    except StockAuditRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"audit": audit_dict(audit, include_items=False)}), 201


@stock_audits_bp.post("/api/v1/audits/<string:audit_id>/start")
@login_required
def start_audit_api(audit_id: str):
    data = _payload()
    try:
        audit = start_stock_audit(
            current_user,
            audit_id=audit_id,
            company_id=data.get("company_id"),
            auditor_id=data.get("auditor_id") or None,
        )
        db.session.commit()
    except StockAuditRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"audit": audit_dict(audit, include_items=False)}), 200


@stock_audits_bp.post("/api/v1/audits/<string:audit_id>/items/<string:item_id>/counts")
@login_required
def record_count_api(audit_id: str, item_id: str):
    data = _payload()
    try:
        count_event = record_count(
            current_user,
            audit_id=audit_id,
            item_id=item_id,
            company_id=data.get("company_id"),
            count=data.get("count"),
            notes=data.get("notes"),
        )
        db.session.commit()
    except StockAuditRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify(
        {
            "count": {
                "id": count_event.id,
                "count": count_event.count,
                "notes": count_event.notes,
            }
        }
    ), 201


@stock_audits_bp.post("/api/v1/audits/<string:audit_id>/items/<string:item_id>/counts/<string:count_event_id>/evidence")
@login_required
def add_evidence_api(audit_id: str, item_id: str, count_event_id: str):
    data = _payload()
    file_storage = request.files.get("file")
    try:
        image = add_count_evidence(
            current_user,
            audit_id=audit_id,
            item_id=item_id,
            count_event_id=count_event_id,
            company_id=data.get("company_id"),
            file_storage=file_storage,
        )
        db.session.commit()
    except StockAuditRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"image": {"id": image.id}}), 201


@stock_audits_bp.post("/api/v1/audits/<string:audit_id>/complete")
@login_required
def complete_audit_api(audit_id: str):
    data = _payload()
    final_counts = data.get("final_counts") or {}
    if not isinstance(final_counts, dict):
        final_counts = {}
    try:
        audit = complete_stock_audit(
            current_user,
            audit_id=audit_id,
            company_id=data.get("company_id"),
            final_counts={str(key): value for key, value in final_counts.items()},
        )
        db.session.commit()
    except StockAuditRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"audit": audit_dict(audit)}), 200


@stock_audits_bp.post("/api/v1/audits/<string:audit_id>/cancel")
@login_required
def cancel_audit_api(audit_id: str):
    data = _payload()
    try:
        audit = cancel_stock_audit(
            current_user,
            audit_id=audit_id,
            company_id=data.get("company_id"),
            reason=data.get("reason"),
        )
        db.session.commit()
    except StockAuditRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"audit": audit_dict(audit, include_items=False)}), 200


@stock_audits_bp.get("/api/v1/audits/<string:audit_id>/counts/<string:item_id>")
@login_required
def audit_counts_api(audit_id: str, item_id: str):
    try:
        counts = audit_counts(current_user, audit_id=audit_id, item_id=item_id, company_id=request.args.get("company_id"))
    except StockAuditRuleError as error:
        return _error(error)
    return jsonify({"counts": counts}), 200


@stock_audits_bp.get("/api/v1/audits/<string:audit_id>/evidence/<string:count_event_id>")
@login_required
def audit_evidence_api(audit_id: str, count_event_id: str):
    try:
        evidence = audit_evidence(
            current_user,
            audit_id=audit_id,
            count_event_id=count_event_id,
            company_id=request.args.get("company_id"),
        )
    except StockAuditRuleError as error:
        return _error(error)
    return jsonify({"evidence": evidence}), 200


@stock_audits_bp.get("/audits/<string:audit_id>")
@login_required
def audit_detail_page(audit_id: str):
    company = _resolve_company()
    if company is None:
        abort(404)
    try:
        from .service import _audit_for_actor

        audit = _audit_for_actor(current_user, audit_id, company_id=company.id)
        data = audit_dict(audit)
    except StockAuditRuleError as error:
        abort(error.status_code)
    return render_template("stock_audits/detail.html", company=company, audit=data)


@stock_audits_bp.get("/audits/<string:audit_id>/report")
@login_required
def audit_report_page(audit_id: str):
    company = _resolve_company()
    if company is None:
        abort(404)
    try:
        from .service import _audit_for_actor

        audit = _audit_for_actor(current_user, audit_id, company_id=company.id)
        data = audit_dict(audit)
    except StockAuditRuleError as error:
        abort(error.status_code)
    return render_template("stock_audits/report.html", company=company, audit=data)
