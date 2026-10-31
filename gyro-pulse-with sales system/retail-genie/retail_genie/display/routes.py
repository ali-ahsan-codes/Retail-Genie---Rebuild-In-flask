"""Read-only LCD order display; always limited to assigned stores."""

from flask import abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership
from ..extensions import db
from ..models import Company, SalesOrder, SalesOrderLine, Store
from . import display_bp


def _display_orders(store_id: str | None):
    if current_user.is_super_admin:
        abort(403)
    if current_user.effective_role != "display" and not current_user.has_permission("view_admin_dashboard"):
        abort(403)
    membership = current_membership(current_user)
    if membership is None or not membership.company_id:
        abort(403)
    company = db.session.get(Company, membership.company_id)
    if company is None or not company.is_active:
        abort(404)
    allowed = accessible_store_ids(current_user, company_id=company.id, tenant_container_id=company.tenant_container_id)
    if store_id:
        if store_id not in allowed:
            abort(403)
        selected = db.session.get(Store, store_id)
    elif allowed:
        selected = db.session.execute(
            select(Store).where(Store.id.in_(allowed), Store.is_active.is_(True)).order_by(Store.code.asc()).limit(1)
        ).scalar_one_or_none()
    else:
        abort(403)
    if selected is None:
        abort(404)
    orders = db.session.execute(
        select(SalesOrder).where(
            SalesOrder.tenant_container_id == company.tenant_container_id,
            SalesOrder.company_id == company.id,
            SalesOrder.origin_store_id == selected.id,
            SalesOrder.status == "open",
        ).order_by(SalesOrder.created_at.asc()).limit(100)
    ).scalars().all()
    display_orders = []
    for order in orders:
        lines = db.session.execute(select(SalesOrderLine).where(
            SalesOrderLine.tenant_container_id == company.tenant_container_id,
            SalesOrderLine.company_id == company.id,
            SalesOrderLine.order_id == order.id,
            SalesOrderLine.is_active.is_(True),
        ).order_by(SalesOrderLine.created_at.asc())).scalars()
        display_orders.append({
            "id": order.id,
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "status": order.status,
            "total_amount": format(order.total_amount, ".3f"),
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "items": [{"name": line.name, "quantity": line.quantity} for line in lines],
        })
    return selected, display_orders


@display_bp.get("/lcd-display")
@login_required
def lcd_display_page():
    store, orders = _display_orders(request.args.get("store_id"))
    return render_template("display/lcd.html", store=store, orders=orders)


@display_bp.get("/api/v1/display/orders")
@login_required
def display_orders_api():
    store, orders = _display_orders(request.args.get("store_id"))
    return jsonify({"store": {"id": store.id, "name": store.name}, "orders": orders}), 200
