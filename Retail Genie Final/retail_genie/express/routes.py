"""Restricted atomic express-checkout API and page."""

from flask import abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func, select

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import CatalogProduct, Company, InventoryMovement, Store
from ..sales.service import SalesRuleError, express_checkout, order_dict
from . import express_bp


def _payload() -> dict:
    if request.is_json:
        value = request.get_json(silent=True)
        return value if isinstance(value, dict) else {}
    return request.form.to_dict(flat=True)


def _require_express():
    if not current_user.has_permission("express_checkout"):
        abort(403)
    if current_user.is_super_admin:
        abort(403)
    membership = current_membership(current_user)
    if membership is None or not membership.company_id:
        abort(403)
    company = db.session.get(Company, membership.company_id)
    if company is None or not company.is_active:
        abort(404)
    store_ids = accessible_store_ids(current_user, company_id=company.id, tenant_container_id=company.tenant_container_id)
    stores = list(db.session.execute(select(Store).where(Store.id.in_(store_ids), Store.is_active.is_(True)).order_by(Store.code.asc())).scalars()) if store_ids else []
    return company, stores


@express_bp.get("/express")
@login_required
def express_page():
    company, stores = _require_express()
    return render_template("express/checkout.html", company=company, stores=stores)


@express_bp.get("/api/v1/express/products")
@login_required
def express_products_api():
    company, stores = _require_express()
    store_id = request.args.get("store_id")
    if not store_id or store_id not in {store.id for store in stores}:
        return jsonify(error="store_forbidden", message="Choose an assigned store."), 403
    if not can_access_data_domain(current_user, tenant_container_id=company.tenant_container_id, domain="product_catalog", action="view", company_id=company.id) or not can_access_data_domain(current_user, tenant_container_id=company.tenant_container_id, domain="inventory", action="view", company_id=company.id, store_id=store_id):
        return jsonify(error="permission_denied", message="Catalog and inventory view access is required."), 403
    term = (request.args.get("q") or "").strip()[:80]
    statement = select(CatalogProduct).where(
        CatalogProduct.tenant_container_id == company.tenant_container_id,
        CatalogProduct.company_id == company.id,
        CatalogProduct.is_active.is_(True),
    )
    if term:
        statement = statement.where(
            CatalogProduct.sku.ilike(f"%{term}%")
            | CatalogProduct.barcode.ilike(f"%{term}%")
            | CatalogProduct.name.ilike(f"%{term}%")
        )
    products = db.session.execute(statement.order_by(CatalogProduct.name.asc()).limit(30)).scalars()
    rows = []
    for product in products:
        stock = db.session.execute(
            select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(
                InventoryMovement.tenant_container_id == company.tenant_container_id,
                InventoryMovement.company_id == company.id,
                InventoryMovement.store_id == store_id,
                InventoryMovement.product_owner_company_id == product.company_id,
                InventoryMovement.product_id == product.id,
            )
        ).scalar_one()
        rows.append({"id": product.id, "sku": product.sku, "barcode": product.barcode, "name": product.name, "price": str(product.price) if product.price is not None else None, "quantity_on_hand": int(stock or 0)})
    return jsonify({"products": rows}), 200


@express_bp.post("/api/v1/express/checkout")
@login_required
def express_checkout_api():
    _require_express()
    data = _payload()
    try:
        order, replayed = express_checkout(
            current_user._get_current_object(),
            company_id=data.get("company_id"),
            store_id=str(data.get("store_id", "")),
            items=data.get("items"),
            payments=data.get("payments"),
            idempotency_key=data.get("idempotency_key", ""),
            customer_phone=data.get("customer_phone", ""),
            customer_name=data.get("customer_name"),
        )
        # express_checkout commits a single transaction. Replay is reported
        # without creating additional payments or stock movements.
    except SalesRuleError as error:
        db.session.rollback()
        return jsonify(error=error.code, message=str(error)), error.status_code
    return jsonify({"order": order_dict(order), "replayed": replayed}), 200 if replayed else 201
