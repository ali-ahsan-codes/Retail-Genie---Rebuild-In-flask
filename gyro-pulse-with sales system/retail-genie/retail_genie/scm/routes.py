"""SCM pages and JSON APIs: suppliers, purchase orders, receiving, logistics."""

from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from ..auth.tenant_context import current_membership, current_tenant_container_id
from ..auth.store_scope import accessible_store_ids
from ..catalog.service import CatalogRuleError
from ..extensions import db
from ..models import CatalogProduct, Company, PurchaseOrder, Store, Supplier
from . import scm_bp
from .service import (
    ScmRuleError,
    cancel_purchase_order,
    add_po_attachment,
    add_supplier_attachment,
    confirm_purchase_order,
    create_purchase_order,
    create_supplier,
    get_po_attachment,
    get_supplier_attachment,
    link_supplier_product,
    list_purchase_orders,
    list_supplier_attachments,
    list_supplier_products,
    list_suppliers,
    purchase_order_dict,
    receive_purchase_order,
    remove_supplier_product,
    set_supplier_status,
    update_purchase_order,
    update_purchase_order_logistics,
    update_supplier,
)


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict(flat=True)


def _error(error: ScmRuleError):
    return jsonify(error=error.code, message=str(error)), error.status_code


def _resolve_company():
    if current_user.is_super_admin:
        company_id = request.args.get("company_id") or request.form.get("company_id")
        company = db.session.get(Company, company_id) if company_id else None
        if company is None or not company.is_active:
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
    membership = current_membership(current_user)
    if membership is None or not membership.company_id:
        return None, []
    company = db.session.get(Company, membership.company_id)
    if company is None or not company.is_active:
        return None, []
    return company, []


def _scm_context(template: str):
    company, companies = _resolve_company()
    if company is None:
        return render_template(template, company=None, companies=[], suppliers=[], purchase_orders=[], products=[])
    suppliers = []
    purchase_orders = []
    products = []
    try:
        suppliers = list_suppliers(current_user, company_id=company.id)
        purchase_orders = list_purchase_orders(current_user, company_id=company.id)
        products = list(db.session.execute(select(CatalogProduct).where(CatalogProduct.tenant_container_id == company.tenant_container_id, CatalogProduct.company_id == company.id, CatalogProduct.is_active.is_(True)).order_by(CatalogProduct.name.asc()).limit(500)).scalars())
    except ScmRuleError:
        suppliers = []
        purchase_orders = []
        products = []
    return render_template(
        template,
        company=company,
        companies=companies,
        suppliers=suppliers,
        purchase_orders=purchase_orders,
        products=products,
    )


@scm_bp.get("/scm")
@login_required
def scm_dashboard():
    return _scm_context("scm/dashboard.html")


# ------------------------------------------------------------------ suppliers

@scm_bp.post("/api/v1/suppliers")
@login_required
def create_supplier_api():
    data = _payload()
    try:
        supplier = create_supplier(
            current_user,
            company_id=data.get("company_id"),
            name=data.get("name"),
            contact_email=data.get("contact_email"),
            phone=data.get("phone"),
            lead_time=data.get("lead_time"),
            notes=data.get("notes"),
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    if not request.is_json:
        return redirect(url_for("scm.suppliers_page"))
    return jsonify({"supplier": {"id": supplier.id, "name": supplier.name}}), 201


@scm_bp.patch("/api/v1/suppliers/<string:supplier_id>")
@login_required
def update_supplier_api(supplier_id: str):
    data = _payload()
    try:
        supplier = update_supplier(
            current_user,
            supplier_id=supplier_id,
            company_id=data.get("company_id"),
            changes={
                key: data.get(key)
                for key in ("name", "contact_email", "phone", "lead_time", "notes")
                if key in data
            },
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"supplier": {"id": supplier.id, "name": supplier.name}}), 200


@scm_bp.post("/api/v1/suppliers/<string:supplier_id>/status")
@login_required
def set_supplier_status_api(supplier_id: str):
    data = _payload()
    active = str(data.get("active", "")).lower() in {"1", "true", "yes", "on"}
    try:
        supplier = set_supplier_status(
            current_user,
            supplier_id=supplier_id,
            company_id=data.get("company_id"),
            active=active,
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"supplier": {"id": supplier.id, "supplier_status": supplier.supplier_status}}), 200


@scm_bp.post("/api/v1/suppliers/<string:supplier_id>/products")
@login_required
def link_supplier_product_api(supplier_id: str):
    data = _payload()
    try:
        link = link_supplier_product(
            current_user,
            supplier_id=supplier_id,
            company_id=data.get("company_id"),
            product_id=data.get("product_id"),
            unit_price=data.get("unit_price"),
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"link": {"id": link.id, "unit_price": str(link.unit_price)}}), 201


@scm_bp.delete("/api/v1/suppliers/products/<string:link_id>")
@login_required
def remove_supplier_product_api(link_id: str):
    data = request.get_json(silent=True) or {}
    try:
        remove_supplier_product(current_user, link_id=link_id, company_id=data.get("company_id"))
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"removed": True}), 200


@scm_bp.post("/api/v1/suppliers/<string:supplier_id>/attachments")
@login_required
def add_supplier_attachment_api(supplier_id: str):
    data = _payload()
    file_storage = request.files.get("file")
    try:
        attachment = add_supplier_attachment(
            current_user,
            supplier_id=supplier_id,
            company_id=data.get("company_id"),
            file_storage=file_storage,
            notes=data.get("notes"),
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"attachment": {"id": attachment.id, "original_name": attachment.original_name}}), 201


@scm_bp.get("/api/v1/suppliers/<string:supplier_id>/attachments")
@login_required
def list_supplier_attachments_api(supplier_id: str):
    company_id = request.args.get("company_id")
    try:
        attachments = list_supplier_attachments(current_user, supplier_id=supplier_id, company_id=company_id)
    except ScmRuleError as error:
        return _error(error)
    return jsonify({"attachments": attachments}), 200


@scm_bp.get("/api/v1/suppliers/<string:supplier_id>/attachments/<string:attachment_id>")
@login_required
def download_supplier_attachment_api(supplier_id: str, attachment_id: str):
    try:
        attachment = get_supplier_attachment(current_user, supplier_id=supplier_id, attachment_id=attachment_id, company_id=request.args.get("company_id"))
    except ScmRuleError as error:
        return _error(error)
    root = Path(current_app.config["UPLOADS_DIR"]).resolve()
    path = (root / attachment.file_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    response = send_file(path, as_attachment=True, download_name=attachment.original_name, conditional=True)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@scm_bp.get("/api/v1/suppliers/<string:supplier_id>/products")
@login_required
def list_supplier_products_api(supplier_id: str):
    company_id = request.args.get("company_id")
    try:
        links = list_supplier_products(current_user, supplier_id=supplier_id, company_id=company_id)
    except ScmRuleError as error:
        return _error(error)
    return jsonify({"links": links}), 200


# ----------------------------------------------------------- purchase orders

@scm_bp.post("/api/v1/purchase-orders")
@login_required
def create_purchase_order_api():
    data = _payload()
    items = data.get("items", [])
    if not isinstance(items, list):
        items = []
    try:
        from datetime import date as _date

        po = create_purchase_order(
            current_user,
            company_id=data.get("company_id"),
            supplier_id=data.get("supplier_id"),
            items=items,
            expected_delivery=data.get("expected_delivery"),
            deadline=data.get("deadline"),
            transportation_details=data.get("transportation_details"),
            advance_paid=data.get("advance_paid"),
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"purchase_order": purchase_order_dict(po)}), 201


@scm_bp.patch("/api/v1/purchase-orders/<string:po_id>")
@login_required
def update_purchase_order_api(po_id: str):
    data = _payload()
    try:
        po = update_purchase_order(
            current_user,
            po_id=po_id,
            company_id=data.get("company_id"),
            changes={key: data.get(key) for key in ("supplier_id", "expected_delivery", "deadline", "transportation_details", "advance_paid", "items") if key in data},
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"purchase_order": purchase_order_dict(po)}), 200


@scm_bp.post("/api/v1/purchase-orders/<string:po_id>/confirm")
@login_required
def confirm_purchase_order_api(po_id: str):
    data = _payload()
    try:
        po = confirm_purchase_order(current_user, po_id=po_id, company_id=data.get("company_id"))
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"purchase_order": purchase_order_dict(po)}), 200


@scm_bp.post("/api/v1/purchase-orders/<string:po_id>/cancel")
@login_required
def cancel_purchase_order_api(po_id: str):
    data = _payload()
    try:
        po = cancel_purchase_order(
            current_user,
            po_id=po_id,
            company_id=data.get("company_id"),
            reason=data.get("reason"),
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"purchase_order": purchase_order_dict(po)}), 200


@scm_bp.post("/api/v1/purchase-orders/<string:po_id>/receive")
@login_required
def receive_purchase_order_api(po_id: str):
    data = _payload()
    receipts = data.get("receipts", [])
    if not isinstance(receipts, list):
        receipts = []
    try:
        po = receive_purchase_order(
            current_user,
            po_id=po_id,
            company_id=data.get("company_id"),
            receipts=receipts,
        )
        realtime_event_ids = list(getattr(po, "_realtime_event_ids", []))
        db.session.commit()
        from ..realtime.service import publish_realtime_event

        for event_id in realtime_event_ids:
            publish_realtime_event(event_id)
    except (ScmRuleError, CatalogRuleError) as error:
        db.session.rollback()
        status_code = getattr(error, "status_code", 400)
        return jsonify(error=getattr(error, "code", "invalid_request"), message=str(error)), status_code
    return jsonify({"purchase_order": purchase_order_dict(po)}), 200


@scm_bp.patch("/api/v1/purchase-orders/<string:po_id>/logistics")
@login_required
def update_po_logistics_api(po_id: str):
    data = _payload()
    try:
        po = update_purchase_order_logistics(
            current_user,
            po_id=po_id,
            company_id=data.get("company_id"),
            logistics_status=data.get("logistics_status"),
            transportation_details=data.get("transportation_details"),
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"purchase_order": purchase_order_dict(po, include_items=False)}), 200


@scm_bp.post("/api/v1/purchase-orders/<string:po_id>/attachments")
@login_required
def add_po_attachment_api(po_id: str):
    data = _payload()
    file_storage = request.files.get("file")
    try:
        attachment = add_po_attachment(
            current_user,
            po_id=po_id,
            company_id=data.get("company_id"),
            file_storage=file_storage,
            attachment_type=str(data.get("attachment_type", "other")),
            notes=data.get("notes"),
        )
        db.session.commit()
    except ScmRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"attachment": {"id": attachment.id, "original_name": attachment.original_name}}), 201


@scm_bp.get("/api/v1/purchase-orders/<string:po_id>/attachments/<string:attachment_id>")
@login_required
def download_po_attachment_api(po_id: str, attachment_id: str):
    try:
        attachment = get_po_attachment(current_user, po_id=po_id, attachment_id=attachment_id, company_id=request.args.get("company_id"))
    except ScmRuleError as error:
        return _error(error)
    root = Path(current_app.config["UPLOADS_DIR"]).resolve()
    path = (root / attachment.file_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=attachment.original_name, conditional=True)


@scm_bp.get("/api/v1/purchase-orders/<string:po_id>")
@login_required
def get_purchase_order_api(po_id: str):
    company_id = request.args.get("company_id") or request.form.get("company_id")
    tenant_id = current_tenant_container_id(current_user)
    if not tenant_id:
        return jsonify(error="tenant_forbidden"), 403
    po = db.session.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.tenant_container_id == tenant_id,
        )
    ).scalar_one_or_none()
    if po is None or (company_id and po.company_id != company_id):
        return jsonify(error="not_found"), 404
    try:
        list_purchase_orders(current_user, company_id=po.company_id)
    except ScmRuleError as error:
        return _error(error)
    return jsonify({"purchase_order": purchase_order_dict(po)}), 200


# -------------------------------------------------------------------- pages

@scm_bp.get("/scm/suppliers")
@login_required
def suppliers_page():
    company, companies = _resolve_company()
    if company is None:
        return render_template("scm/suppliers.html", company=None, companies=[], suppliers=[], products=[])
    products = list(
        db.session.execute(
            select(CatalogProduct)
            .where(
                CatalogProduct.tenant_container_id == company.tenant_container_id,
                CatalogProduct.company_id == company.id,
                CatalogProduct.is_active.is_(True),
            )
            .order_by(CatalogProduct.name.asc())
            .limit(500)
        )
        .scalars()
    )
    try:
        suppliers = list_suppliers(current_user, company_id=company.id, include_inactive=True)
    except ScmRuleError:
        suppliers = []
    return render_template(
        "scm/suppliers.html",
        company=company,
        companies=companies,
        suppliers=suppliers,
        products=products,
    )


@scm_bp.get("/scm/suppliers/<string:supplier_id>")
@login_required
def supplier_detail_page(supplier_id: str):
    company, companies = _resolve_company()
    if company is None:
        abort(404)
    supplier = db.session.execute(select(Supplier).where(
        Supplier.id == supplier_id,
        Supplier.tenant_container_id == company.tenant_container_id,
        Supplier.company_id == company.id,
    )).scalar_one_or_none()
    if supplier is None:
        abort(404)
    try:
        attachments = list_supplier_attachments(current_user, supplier_id=supplier.id, company_id=company.id)
        products = list_supplier_products(current_user, supplier_id=supplier.id, company_id=company.id)
    except ScmRuleError as error:
        abort(error.status_code)
    return render_template("scm/supplier_detail.html", company=company, companies=companies, supplier=supplier, attachments=attachments, products=products)


@scm_bp.get("/scm/purchase-orders")
@login_required
def purchase_orders_page():
    return _scm_context("scm/purchase_orders.html")


@scm_bp.get("/scm/purchase-orders/<string:po_id>")
@login_required
def purchase_order_page(po_id: str):
    company, companies = _resolve_company()
    if company is None:
        abort(404)
    try:
        po = db.session.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.id == po_id,
                PurchaseOrder.tenant_container_id == company.tenant_container_id,
                PurchaseOrder.company_id == company.id,
            )
        ).scalar_one_or_none()
        if po is None:
            abort(404)
        data = purchase_order_dict(po)
        allowed = accessible_store_ids(current_user, company_id=company.id, tenant_container_id=company.tenant_container_id)
        stores = []
        if allowed:
            stores = list(
                db.session.execute(
                    select(Store)
                    .where(Store.id.in_(allowed), Store.is_active.is_(True))
                    .order_by(Store.code.asc())
                )
                .scalars()
            )
        supplier = db.session.get(Supplier, po.supplier_id)
        return render_template(
            "scm/purchase_order.html",
            company=company,
            companies=companies,
            purchase_order=data,
            supplier=supplier,
            stores=stores,
        )
    except ScmRuleError as error:
        abort(error.status_code)
