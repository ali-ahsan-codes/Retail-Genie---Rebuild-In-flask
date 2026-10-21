"""JSON endpoints and lightweight server-rendered screens for core retail workflows."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership, current_tenant_container_id
from ..extensions import db
from ..models import Company, DailyCashup, OrderRemovalRequest, OrderReturn, OrderReturnLine, SalesOrder, SalesOrderLine, Store, StoreCredit
from . import sales_bp
from .service import (
    SalesRuleError,
    _company_for_actor,
    _order_for_actor,
    company_today,
    find_open_orders,
    find_returnable_orders,
    find_store_credits,
    list_sales_orders,
    order_dict,
    process_order_return,
    review_cashup,
    review_removal_request,
    add_order_item,
    create_order,
    record_payment,
    redeem_store_credit,
    request_item_removal,
    submit_cashup,
    update_order_fulfillment,
)


def _payload() -> dict:
    value = request.get_json(silent=True)
    if value is None:
        value = request.form.to_dict(flat=True)
    return value if isinstance(value, dict) else {}


def _error_response(error: SalesRuleError):
    db.session.rollback()
    return jsonify(error=error.code, message=str(error)), error.status_code


def _parse_business_date(value, company: Company) -> date:
    if not value:
        return company_today(company)
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise SalesRuleError("Business date must use YYYY-MM-DD.") from None


def _cashup_dict(cashup: DailyCashup) -> dict:
    return {
        "id": cashup.id,
        "company_id": cashup.company_id,
        "store_id": cashup.store_id,
        "business_date": cashup.business_date.isoformat(),
        "submitted_by_id": cashup.submitted_by_id,
        "expected": {
            "cash": format(cashup.expected_cash, ".3f"),
            "bank": format(cashup.expected_bank, ".3f"),
            "bank_transfer": format(cashup.expected_bank_transfer, ".3f"),
            "other": format(cashup.expected_other, ".3f"),
        },
        "counted": {
            "cash": format(cashup.counted_cash, ".3f"),
            "bank": format(cashup.counted_bank, ".3f"),
            "bank_transfer": format(cashup.counted_bank_transfer, ".3f"),
            "other": format(cashup.counted_other, ".3f"),
        },
        "variance": {key: format(value, ".3f") for key, value in cashup.variances.items()},
        "status": cashup.status,
        "notes": cashup.notes,
        "review_note": cashup.review_note,
        "submitted_at": cashup.submitted_at.isoformat() if cashup.submitted_at else None,
        "reviewed_at": cashup.reviewed_at.isoformat() if cashup.reviewed_at else None,
    }


@sales_bp.get("/pos")
@login_required
def point_of_sale():
    if not current_user.has_permission("use_sales_pos"):
        abort(403)
    companies = Company.query.filter_by(is_active=True).order_by(Company.name.asc()).all() if current_user.is_super_admin else []
    if current_user.is_super_admin:
        company_id = request.args.get("company_id")
        company = db.session.get(Company, company_id) if company_id else None
        if company is None:
            return render_template("sales/pos.html", company=None, stores=[], companies=companies), 200
    else:
        membership = current_membership(current_user)
        company = db.session.get(Company, membership.company_id) if membership and membership.company_id else None
    stores = []
    if company and company.is_active:
        allowed = accessible_store_ids(current_user, company_id=company.id)
        stores = Store.query.filter(Store.id.in_(allowed), Store.is_active.is_(True)).order_by(Store.code.asc()).all() if allowed else []
    return render_template("sales/pos.html", company=company, stores=stores, companies=companies)


@sales_bp.get("/api/v1/orders/open")
@login_required
def open_orders():
    try:
        orders = find_open_orders(
            current_user,
            store_id=request.args.get("store_id", ""),
            phone=request.args.get("phone", ""),
            company_id=request.args.get("company_id"),
        )
        return jsonify(orders=orders)
    except SalesRuleError as error:
        return _error_response(error)


@sales_bp.post("/api/v1/orders")
@login_required
def create_sales_order():
    data = _payload()
    try:
        order = create_order(
            current_user,
            store_id=str(data.get("store_id", "")),
            customer_phone=data.get("customer_phone", ""),
            customer_name=data.get("customer_name"),
            items=data.get("items"),
            company_id=data.get("company_id"),
            discount_percentage=data.get("discount_percentage"),
            primary_salesperson_id=data.get("primary_salesperson_id"),
            secondary_salesperson_id=data.get("secondary_salesperson_id"),
            delivery_address=data.get("delivery_address"),
            storekeeper_notes=data.get("storekeeper_notes"),
            cashier_notes=data.get("cashier_notes"),
            reminder_date=data.get("reminder_date"),
            reminder_notes=data.get("reminder_notes"),
        )
        return jsonify(order=order_dict(order)), 201
    except SalesRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The order could not be saved; reload and retry."), 409


@sales_bp.get("/api/v1/orders/<string:order_id>")
@login_required
def get_sales_order(order_id: str):
    try:
        order, _store, _company = _order_for_actor(
            current_user,
            order_id,
            request.args.get("store_id", ""),
        )
        return jsonify(order=order_dict(order))
    except SalesRuleError as error:
        return _error_response(error)


@sales_bp.patch("/api/v1/orders/<string:order_id>/fulfillment")
@login_required
def update_order_fulfillment_api(order_id: str):
    data = _payload()
    try:
        order = update_order_fulfillment(current_user, order_id=order_id, company_id=data.get("company_id"), status=str(data.get("delivery_status", "")), delivery_address=data.get("delivery_address"), storekeeper_notes=data.get("storekeeper_notes"))
        return jsonify(order=order_dict(order)), 200
    except SalesRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The fulfillment update conflicted; retry after refreshing."), 409


@sales_bp.get("/api/v1/orders")
@login_required
def list_sales_orders_api():
    try:
        rows = list_sales_orders(current_user, company_id=request.args.get("company_id"), store_id=request.args.get("store_id"), status=request.args.get("status", "all"), search=request.args.get("q"))
        return jsonify(orders=rows), 200
    except SalesRuleError as error:
        return _error_response(error)


@sales_bp.get("/admin/orders")
@login_required
def admin_orders_page():
    companies = []
    if current_user.is_super_admin and not request.args.get("company_id"):
        tenant_id = current_tenant_container_id(current_user)
        companies = Company.query.filter_by(tenant_container_id=tenant_id, is_active=True).order_by(Company.name.asc()).all() if tenant_id else []
        return render_template("sales/orders.html", company=None, companies=companies, stores=[], orders=[], status="all", search="")
    try:
        company = _company_for_actor(current_user, request.args.get("company_id"))
        store_ids = accessible_store_ids(current_user, company_id=company.id, tenant_container_id=company.tenant_container_id)
        stores = Store.query.filter(Store.id.in_(store_ids), Store.is_active.is_(True)).order_by(Store.code.asc()).all() if store_ids else []
        if not (current_user.is_admin or current_user.has_permission("manage_orders") or current_user.has_permission("sales.view")):
            abort(403)
        orders = list_sales_orders(current_user, company_id=company.id, store_id=request.args.get("store_id") or None, status=request.args.get("status", "all"), search=request.args.get("q", ""))
    except SalesRuleError as error:
        abort(error.status_code)
    return render_template("sales/orders.html", company=company, companies=companies, stores=stores, orders=orders, status=request.args.get("status", "all"), search=request.args.get("q", ""))


@sales_bp.get("/sales/orders/<string:order_id>/print")
@login_required
def print_sales_order(order_id: str):
    try:
        company = _company_for_actor(current_user, request.args.get("company_id"))
        order_ref = db.session.execute(select(SalesOrder).where(SalesOrder.id == order_id, SalesOrder.tenant_container_id == company.tenant_container_id, SalesOrder.company_id == company.id)).scalar_one_or_none()
        if order_ref is None:
            abort(404)
        order, _store, _company = _order_for_actor(current_user, order_id, order_ref.origin_store_id, for_shared_bill=False)
    except SalesRuleError as error:
        abort(error.status_code)
    return render_template("sales/order_print.html", order=order_dict(order), company=company)


@sales_bp.get("/sales/returns/<string:return_id>/print")
@login_required
def print_return_slip(return_id: str):
    try:
        company = _company_for_actor(current_user, request.args.get("company_id"))
        record = db.session.execute(select(OrderReturn).where(OrderReturn.id == return_id, OrderReturn.tenant_container_id == company.tenant_container_id, OrderReturn.company_id == company.id)).scalar_one_or_none()
        if record is None:
            abort(404)
        order, _store, _company = _order_for_actor(current_user, record.order_id, record.store_id, for_shared_bill=False)
        rows = db.session.execute(select(OrderReturnLine, SalesOrderLine.name).join(SalesOrderLine,
            (SalesOrderLine.tenant_container_id == OrderReturnLine.tenant_container_id) &
            (SalesOrderLine.company_id == OrderReturnLine.company_id) &
            (SalesOrderLine.id == OrderReturnLine.sales_order_line_id)
        ).where(OrderReturnLine.tenant_container_id == company.tenant_container_id, OrderReturnLine.company_id == company.id, OrderReturnLine.return_id == record.id)).all()
        details = [{"name": name, "quantity": line.quantity, "unit_price": format(line.unit_price, ".3f"), "line_total": format(line.line_total, ".3f")} for line, name in rows]
        document = {"id": record.id, "kind": record.kind, "refund_method": record.refund_method, "refund_amount": format(record.refund_amount, ".3f"), "reason": record.reason, "transaction_reference": record.transaction_reference, "created_at": record.created_at.isoformat() if record.created_at else None, "items": details}
    except SalesRuleError as error:
        abort(error.status_code)
    return render_template("sales/return_print.html", order=order_dict(order), document=document, company=company)


@sales_bp.post("/api/v1/orders/<string:order_id>/items")
@login_required
def append_sales_order_item(order_id: str):
    data = _payload()
    try:
        order = add_order_item(
            current_user,
            order_id=order_id,
            store_id=str(data.get("store_id", "")),
            item=data,
        )
        return jsonify(order=order_dict(order)), 200
    except SalesRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The item could not be added; reload and retry."), 409


@sales_bp.post("/api/v1/orders/<string:order_id>/items/<string:line_id>/removal-requests")
@login_required
def request_sales_order_item_removal(order_id: str, line_id: str):
    data = _payload()
    try:
        removal = request_item_removal(
            current_user,
            order_id=order_id,
            store_id=str(data.get("store_id", "")),
            line_id=line_id,
            quantity=data.get("quantity_to_remove"),
            reason=str(data.get("reason", "")),
        )
        return jsonify(removal_request={"id": removal.id, "status": removal.status, "reason": removal.reason}), 201
    except SalesRuleError as error:
        return _error_response(error)


@sales_bp.post("/api/v1/order-removal-requests/<string:request_id>/review")
@login_required
def review_sales_order_item_removal(request_id: str):
    data = _payload()
    decision = data.get("decision")
    if decision not in {"approve", "reject"}:
        return jsonify(error="invalid_request", message="Decision must be approve or reject."), 400
    try:
        removal = review_removal_request(
            current_user,
            request_id=request_id,
            approve=decision == "approve",
            review_reason=data.get("review_reason"),
        )
        return jsonify(removal_request={"id": removal.id, "status": removal.status}), 200
    except SalesRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The request changed concurrently; reload and retry."), 409


@sales_bp.post("/api/v1/orders/<string:order_id>/payments")
@login_required
def create_order_payment(order_id: str):
    data = _payload()
    try:
        order, payment, replayed = record_payment(
            current_user,
            order_id=order_id,
            store_id=str(data.get("store_id", "")),
            method=str(data.get("method", "")),
            amount=data.get("amount"),
            idempotency_key=data.get("idempotency_key"),
            transaction_reference=data.get("transaction_reference"),
        )
        return jsonify(
            order=order_dict(order),
            payment={"id": payment.id, "method": payment.method, "amount": format(payment.amount, ".3f")},
            replayed=replayed,
        ), 200
    except SalesRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="Payment could not be saved; check for a repeated request."), 409


@sales_bp.get("/api/v1/store-credits")
@login_required
def list_store_credits_api():
    try:
        credits = find_store_credits(current_user._get_current_object(), phone=request.args.get("phone", ""), company_id=request.args.get("company_id"))
        return jsonify(credits=[{"id": credit.id, "credit_number": credit.credit_number, "customer_name": credit.customer_name, "remaining_amount": format(credit.remaining_amount, ".3f"), "expires_at": credit.expires_at.isoformat() if credit.expires_at else None} for credit in credits]), 200
    except SalesRuleError as error:
        return _error_response(error)


@sales_bp.post("/api/v1/orders/<string:order_id>/store-credits/<string:credit_id>/redeem")
@login_required
def redeem_store_credit_api(order_id: str, credit_id: str):
    data = _payload()
    try:
        order, redemption, replayed = redeem_store_credit(
            current_user._get_current_object(),
            credit_id=credit_id,
            order_id=order_id,
            store_id=str(data.get("store_id", "")),
            customer_phone=data.get("customer_phone", ""),
            amount=data.get("amount"),
            idempotency_key=data.get("idempotency_key", ""),
        )
        return jsonify(order=order_dict(order), redemption={"id": redemption.id, "amount": format(redemption.amount, ".3f"), "store_credit_id": redemption.store_credit_id}, replayed=replayed), 200 if replayed else 201
    except SalesRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="Store credit could not be applied; retry with the same request key."), 409


@sales_bp.post("/api/v1/orders/<string:order_id>/returns")
@login_required
def create_order_return(order_id: str):
    data = _payload()
    try:
        order, return_record, replayed = process_order_return(
            current_user,
            order_id=order_id,
            store_id=str(data.get("store_id", "")),
            items=data.get("items"),
            reason=data.get("reason", ""),
            refund_method=str(data.get("refund_method", "")),
            idempotency_key=data.get("idempotency_key"),
            transaction_reference=data.get("transaction_reference"),
            kind=data.get("kind", "refund"),
            exchange_items=data.get("exchange_items"),
            customer_name=data.get("customer_name"),
        )
        result = {
            "id": return_record.id,
            "order_id": return_record.order_id,
            "store_id": return_record.store_id,
            "refund_method": return_record.refund_method,
            "refund_amount": format(return_record.refund_amount, ".3f"),
            "reason": return_record.reason,
            "transaction_reference": return_record.transaction_reference,
            "created_at": return_record.created_at.isoformat() if return_record.created_at else None,
        }
        credit = StoreCredit.query.filter_by(
            tenant_container_id=return_record.tenant_container_id,
            company_id=return_record.company_id,
            source_return_id=return_record.id,
        ).first() if return_record.kind == "store_credit" else None
        credit_result = None if credit is None else {
            "id": credit.id,
            "credit_number": credit.credit_number,
            "amount": format(credit.amount, ".3f"),
            "remaining_amount": format(credit.remaining_amount, ".3f"),
        }
        return jsonify(order=order_dict(order), return_transaction=result, store_credit=credit_result, replayed=replayed), (200 if replayed else 201)
    except SalesRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="The refund could not be saved; retry with the same idempotency key."), 409


@sales_bp.post("/api/v1/cashups")
@login_required
def create_daily_cashup():
    data = _payload()
    try:
        company = _company_for_actor(current_user, data.get("company_id"))
        business_date = _parse_business_date(data.get("business_date"), company)
        counted = data.get("counted")
        if not isinstance(counted, dict):
            counted = {method: data.get(f"counted_{method}", 0) for method in ("cash", "bank", "bank_transfer", "other")}
        cashup = submit_cashup(
            current_user,
            store_id=str(data.get("store_id", "")),
            business_date=business_date,
            counted=counted,
            notes=data.get("notes"),
            company_id=data.get("company_id"),
        )
        return jsonify(cashup=_cashup_dict(cashup)), 201
    except SalesRuleError as error:
        return _error_response(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="integrity_conflict", message="A closeout already exists for this store, date, and manager."), 409


@sales_bp.get("/api/v1/cashups")
@login_required
def list_daily_cashups():
    try:
        company = _company_for_actor(current_user, request.args.get("company_id"))
        query = DailyCashup.query.filter_by(tenant_container_id=company.tenant_container_id, company_id=company.id)
        if current_user.is_super_admin or current_user.is_company_admin:
            store_id = request.args.get("store_id")
            if store_id:
                query = query.filter_by(store_id=store_id)
        else:
            store_ids = accessible_store_ids(current_user, company_id=company.id)
            if not store_ids:
                return jsonify(cashups=[])
            query = query.filter(DailyCashup.store_id.in_(store_ids))
        business_date = request.args.get("business_date")
        if business_date:
            query = query.filter_by(business_date=_parse_business_date(business_date, company))
        rows = query.order_by(DailyCashup.business_date.desc(), DailyCashup.submitted_at.desc()).limit(200).all()
        return jsonify(cashups=[_cashup_dict(row) for row in rows])
    except SalesRuleError as error:
        return _error_response(error)


@sales_bp.post("/api/v1/cashups/<string:cashup_id>/review")
@login_required
def review_daily_cashup(cashup_id: str):
    data = _payload()
    decision = data.get("decision")
    if decision not in {"approve", "reject"}:
        return jsonify(error="invalid_request", message="Decision must be approve or reject."), 400
    try:
        cashup = review_cashup(
            current_user,
            cashup_id=cashup_id,
            approve=decision == "approve",
            note=data.get("note"),
        )
        return jsonify(cashup=_cashup_dict(cashup))
    except SalesRuleError as error:
        return _error_response(error)


@sales_bp.errorhandler(403)
def sales_forbidden(_error):
    return jsonify(error="forbidden"), 403


@sales_bp.errorhandler(404)
def sales_not_found(_error):
    return jsonify(error="not_found"), 404


def _removal_dict(removal: OrderRemovalRequest) -> dict:
    order = SalesOrder.query.filter_by(
        tenant_container_id=removal.tenant_container_id,
        company_id=removal.company_id,
        id=removal.order_id,
    ).first()
    line = SalesOrderLine.query.filter_by(
        tenant_container_id=removal.tenant_container_id,
        company_id=removal.company_id,
        id=removal.line_id,
    ).first()
    return {
        "id": removal.id,
        "order_id": removal.order_id,
        "store_id": removal.requesting_store_id,
        "customer_phone": order.customer_phone if order else "",
        "customer_name": order.customer_name if order else None,
        "business_date": order.business_date.isoformat() if order else None,
        "item_name": line.name if line else "(item no longer available)",
        "line_quantity": line.quantity if line else 0,
        "quantity_to_remove": removal.quantity_to_remove,
        "reason": removal.reason,
        "status": removal.status,
        "requested_by_id": removal.requested_by_id,
        "requested_at": removal.created_at.isoformat() if removal.created_at else None,
    }


@sales_bp.get("/returns")
@login_required
def returns_page():
    if not (current_user.effective_role == "manager" or current_user.is_company_admin or current_user.is_super_admin):
        abort(403)
    if not current_user.has_permission("use_sales_pos"):
        abort(403)
    companies = Company.query.filter_by(is_active=True).order_by(Company.name.asc()).all() if current_user.is_super_admin else []
    try:
        company = _company_for_actor(current_user, request.args.get("company_id"))
    except SalesRuleError:
        company = None
    if current_user.is_super_admin and company is None:
        return render_template(
            "sales/returns.html",
            company=None,
            companies=companies,
            stores=[],
            orders=[],
            search=request.args.get("q", ""),
            selected_store_id="",
        )
    store_ids = accessible_store_ids(current_user, company_id=company.id)
    stores = Store.query.filter(
        Store.id.in_(store_ids),
        Store.tenant_container_id == company.tenant_container_id,
        Store.is_active.is_(True),
    ).order_by(Store.code.asc()).all() if store_ids else []
    selected_store_id = request.args.get("store_id", "")
    if selected_store_id not in {store.id for store in stores}:
        selected_store_id = stores[0].id if stores else ""
    search = request.args.get("q", "").strip()[:80]
    orders = []
    if selected_store_id and search:
        try:
            orders = find_returnable_orders(
                current_user,
                store_id=selected_store_id,
                search=search,
                company_id=company.id if current_user.is_super_admin else None,
            )
            for order in orders:
                order["return_idempotency_key"] = str(uuid4())
        except SalesRuleError as error:
            flash(str(error), "error")
    return render_template(
        "sales/returns.html",
        company=company,
        companies=companies,
        stores=stores,
        orders=orders,
        search=search,
        selected_store_id=selected_store_id,
    )


@sales_bp.post("/returns/<string:order_id>")
@login_required
def submit_order_return_page(order_id: str):
    store_id = str(request.form.get("store_id", ""))
    search = str(request.form.get("search", ""))[:80]
    items = []
    print_return_id = None
    return_company_id = request.form.get("company_id")
    for key, value in request.form.items():
        if key.startswith("quantity_") and str(value).strip() not in {"", "0"}:
            items.append({"line_id": key.removeprefix("quantity_"), "quantity": value})
    try:
        _order, return_record, replayed = process_order_return(
            current_user,
            order_id=order_id,
            store_id=store_id,
            items=items,
            reason=request.form.get("reason", ""),
            refund_method=str(request.form.get("refund_method", "")),
            idempotency_key=request.form.get("idempotency_key"),
            transaction_reference=request.form.get("transaction_reference"),
        )
        message = f"Refund of OMR {Decimal(return_record.refund_amount):.3f} recorded by {return_record.refund_method.replace('_', ' ')}."
        flash(("This return was already recorded. " if replayed else "") + message, "success")
        print_return_id = return_record.id
        return_company_id = _order.company_id
    except SalesRuleError as error:
        db.session.rollback()
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("The refund conflicted with another request; reload before retrying.", "error")
    if print_return_id:
        return redirect(url_for("sales.print_return_slip", return_id=print_return_id, company_id=return_company_id))
    return redirect(url_for("sales.returns_page", company_id=return_company_id or None, store_id=store_id, q=search))


@sales_bp.get("/removals")
@login_required
def removal_approvals_page():
    allowed_roles = current_user.effective_role == "manager" or current_user.is_company_admin or current_user.is_super_admin
    if not allowed_roles:
        abort(403)
    companies = Company.query.filter_by(is_active=True).order_by(Company.name.asc()).all() if current_user.is_super_admin else []
    try:
        company = _company_for_actor(current_user, request.args.get("company_id"))
    except SalesRuleError:
        company = None
    if current_user.is_super_admin and company is None:
        return render_template("sales/removal_approvals.html", company=None, companies=companies, stores=[])
    store_ids = accessible_store_ids(current_user, company_id=company.id)
    stores = Store.query.filter(
        Store.id.in_(store_ids),
        Store.tenant_container_id == company.tenant_container_id,
        Store.is_active.is_(True),
    ).order_by(Store.code.asc()).all() if store_ids else []
    return render_template("sales/removal_approvals.html", company=company, companies=companies, stores=stores)


@sales_bp.get("/api/v1/order-removal-requests")
@login_required
def list_order_removal_requests():
    if not (current_user.effective_role == "manager" or current_user.is_company_admin or current_user.is_super_admin):
        return jsonify(error="approval_forbidden", message="Only an authorized manager or administrator can view removal requests."), 403
    try:
        company = _company_for_actor(current_user, request.args.get("company_id"))
        query = OrderRemovalRequest.query.filter_by(tenant_container_id=company.tenant_container_id, company_id=company.id, status="pending")
        if current_user.effective_role == "manager" and not current_user.is_company_admin:
            store_ids = accessible_store_ids(current_user, company_id=company.id)
            if not store_ids:
                return jsonify(removal_requests=[])
            query = query.filter(OrderRemovalRequest.requesting_store_id.in_(store_ids))
        elif request.args.get("store_id"):
            query = query.filter_by(requesting_store_id=request.args.get("store_id"))
        removals = query.order_by(OrderRemovalRequest.created_at.asc()).limit(200).all()
        return jsonify(removal_requests=[_removal_dict(removal) for removal in removals])
    except SalesRuleError as error:
        return _error_response(error)


@sales_bp.get("/cashups")
@login_required
def daily_cashup_page():
    allowed_roles = current_user.effective_role == "manager" or current_user.is_company_admin or current_user.is_super_admin
    if not allowed_roles:
        abort(403)
    companies = Company.query.filter_by(is_active=True).order_by(Company.name.asc()).all() if current_user.is_super_admin else []
    try:
        company = _company_for_actor(current_user, request.args.get("company_id"))
    except SalesRuleError:
        company = None
    if current_user.is_super_admin and company is None:
        return render_template("sales/daily_cashup.html", company=None, companies=companies, stores=[], can_review=True)
    store_ids = accessible_store_ids(current_user, company_id=company.id)
    stores = Store.query.filter(
        Store.id.in_(store_ids),
        Store.tenant_container_id == company.tenant_container_id,
        Store.is_active.is_(True),
    ).order_by(Store.code.asc()).all() if store_ids else []
    return render_template(
        "sales/daily_cashup.html",
        company=company,
        companies=companies,
        stores=stores,
        can_review=current_user.is_company_admin or current_user.is_super_admin,
        today=company_today(company).isoformat(),
    )
