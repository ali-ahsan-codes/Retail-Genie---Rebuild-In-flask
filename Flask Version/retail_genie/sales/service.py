"""Transactional sales logic and server-side authorization for tenant-shared bills."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select

from ..auth.store_scope import can_access_store, can_view_shared_bill
from ..auth.tenant_context import current_membership
from ..extensions import db
from ..models import (
    AuditEvent,
    BillingSeries,
    Company,
    DailyCashup,
    OrderPayment,
    OrderRemovalRequest,
    SalesOrder,
    SalesOrderLine,
    Store,
    TenantContainer,
    User,
)

MONEY_QUANTUM = Decimal("0.001")
ZERO = Decimal("0.000")


class SalesRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def as_money(value, *, field: str = "amount", allow_zero: bool = True) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise SalesRuleError(f"{field} must be a valid OMR amount.")
    try:
        amount = Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise SalesRuleError(f"{field} must be a valid OMR amount.") from None
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount <= 0):
        raise SalesRuleError(f"{field} must be {'greater than zero' if not allow_zero else 'zero or greater'}.")
    if amount >= Decimal("100000000000"):
        raise SalesRuleError(f"{field} exceeds the supported amount.")
    return amount


def normalize_phone(value: str) -> str:
    if not isinstance(value, str):
        raise SalesRuleError("Enter the customer's phone number.")
    digits = re.sub(r"\D", "", value)
    if digits.startswith("00"):
        digits = digits[2:]
    # Accept Oman local numbers with or without the +968 country prefix.
    if digits.startswith("968") and len(digits) == 11:
        digits = digits[3:]
    if not 5 <= len(digits) <= 32:
        raise SalesRuleError("Phone number must contain between 5 and 32 digits.")
    return digits


def _as_integer(value, *, field: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or value is None:
        raise SalesRuleError(f"{field} must be a whole number of at least {minimum}.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise SalesRuleError(f"{field} must be a whole number of at least {minimum}.") from None
    if not number.is_finite() or number != number.to_integral_value() or number < minimum or number > 2147483647:
        raise SalesRuleError(f"{field} must be a whole number of at least {minimum}.")
    return int(number)


def _active_company(company_id: str) -> Company:
    company = db.session.get(Company, company_id)
    if company is None or not company.is_active:
        raise SalesRuleError("Company not found.", 404, "not_found")
    container = db.session.get(TenantContainer, company.tenant_container_id)
    if container is None or not container.is_active:
        raise SalesRuleError("Company not found.", 404, "not_found")
    return company


def _company_for_actor(actor: User, requested_company_id: str | None = None) -> Company:
    if actor.is_super_admin:
        company_id = requested_company_id
        if not company_id:
            raise SalesRuleError("Select a company for this operation.", 400, "company_required")
    else:
        membership = current_membership(actor)
        if membership is None or not membership.company_id:
            raise SalesRuleError("Company not found.", 404, "not_found")
        if requested_company_id and requested_company_id != membership.company_id:
            raise SalesRuleError("Company not found.", 404, "not_found")
        company_id = membership.company_id
    company = _active_company(company_id)
    if not actor.is_super_admin:
        membership = current_membership(actor, tenant_container_id=company.tenant_container_id)
        if membership is None or membership.company_id != company.id:
            raise SalesRuleError("Company not found.", 404, "not_found")
    return company


def company_today(company: Company) -> date:
    try:
        zone = ZoneInfo(company.timezone)
    except ZoneInfoNotFoundError:
        raise SalesRuleError("The company timezone is not configured correctly.", 500, "invalid_company_timezone") from None
    return datetime.now(timezone.utc).astimezone(zone).date()


def _local_day_bounds_utc(company: Company, business_date: date) -> tuple[datetime, datetime]:
    try:
        zone = ZoneInfo(company.timezone)
    except ZoneInfoNotFoundError:
        raise SalesRuleError("The company timezone is not configured correctly.", 500, "invalid_company_timezone") from None
    start_local = datetime.combine(business_date, time.min, tzinfo=zone)
    end_local = datetime.combine(business_date + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _store_for_company(store_id: str, company_id: str) -> Store:
    store = db.session.get(Store, store_id)
    company = db.session.get(Company, company_id)
    if (
        store is None
        or company is None
        or not store.is_active
        or store.company_id != company_id
        or store.tenant_container_id != company.tenant_container_id
    ):
        raise SalesRuleError("Store not found.", 404, "not_found")
    return store


def _require_assigned_store(actor: User, store_id: str, company_id: str) -> Store:
    store = _store_for_company(store_id, company_id)
    if not can_access_store(
        actor,
        store.id,
        company_id=company_id,
        tenant_container_id=store.tenant_container_id,
    ):
        raise SalesRuleError("You do not have access to this store.", 403, "store_forbidden")
    return store


def _order_for_actor(
    actor: User,
    order_id: str,
    acting_store_id: str,
    *,
    for_shared_bill: bool = True,
    lock: bool = False,
) -> tuple[SalesOrder, Store, Company]:
    order_statement = select(SalesOrder).where(SalesOrder.id == order_id)
    if not actor.is_super_admin:
        membership = current_membership(actor)
        if membership is None:
            raise SalesRuleError("Order not found.", 404, "not_found")
        order_statement = order_statement.where(SalesOrder.tenant_container_id == membership.tenant_container_id)
    if lock:
        order_statement = order_statement.with_for_update()
    order = db.session.execute(order_statement).scalar_one_or_none()
    if order is None:
        raise SalesRuleError("Order not found.", 404, "not_found")
    if not actor.is_super_admin:
        membership = current_membership(actor, tenant_container_id=order.tenant_container_id)
        if membership is None or membership.company_id != order.company_id:
            raise SalesRuleError("Order not found.", 404, "not_found")
    company = _active_company(order.company_id)
    store = _store_for_company(acting_store_id, order.company_id)
    if store.tenant_container_id != order.tenant_container_id:
        raise SalesRuleError("Order not found.", 404, "not_found")
    if for_shared_bill and store.id != order.origin_store_id:
        allowed = can_view_shared_bill(
            actor,
            store.id,
            company_id=order.company_id,
            tenant_container_id=order.tenant_container_id,
        )
    else:
        allowed = can_access_store(
            actor,
            store.id,
            company_id=order.company_id,
            tenant_container_id=order.tenant_container_id,
        )
    if not allowed:
        raise SalesRuleError("You are not authorized to use this bill at the selected store.", 403, "bill_forbidden")
    return order, store, company


def _paid_amount(order: SalesOrder) -> Decimal:
    value = db.session.execute(
        select(func.coalesce(func.sum(OrderPayment.amount), 0)).where(
            OrderPayment.tenant_container_id == order.tenant_container_id,
            OrderPayment.company_id == order.company_id,
            OrderPayment.order_id == order.id,
        )
    ).scalar_one()
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM)


def order_dict(order: SalesOrder) -> dict:
    paid = _paid_amount(order)
    lines = SalesOrderLine.query.filter_by(tenant_container_id=order.tenant_container_id, company_id=order.company_id, order_id=order.id, is_active=True).order_by(SalesOrderLine.created_at.asc()).all()
    payments = OrderPayment.query.filter_by(tenant_container_id=order.tenant_container_id, company_id=order.company_id, order_id=order.id).order_by(OrderPayment.created_at.asc()).all()
    return {
        "id": order.id,
        "company_id": order.company_id,
        "origin_store_id": order.origin_store_id,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "business_date": order.business_date.isoformat(),
        "status": order.status,
        "items": [
            {
                "id": line.id,
                "name": line.name,
                "sku": line.sku,
                "quantity": line.quantity,
                "unit_price": format(Decimal(line.unit_price), ".3f"),
                "line_total": format(Decimal(line.line_total), ".3f"),
                "added_store_id": line.added_store_id,
            }
            for line in lines
        ],
        "payments": [
            {
                "id": payment.id,
                "method": payment.method,
                "amount": format(Decimal(payment.amount), ".3f"),
                "store_id": payment.store_id,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
            }
            for payment in payments
        ],
        "total_amount": format(Decimal(order.total_amount), ".3f"),
        "paid_amount": format(paid, ".3f"),
        "balance": format(max(Decimal(order.total_amount) - paid, ZERO), ".3f"),
        "invoice_category": order.invoice_category,
        "invoice_number": order.invoice_number,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "closed_at": order.closed_at.isoformat() if order.closed_at else None,
    }


def _add_audit(company_id: str, actor_id: str | None, action: str, entity_type: str, entity_id: str, *, store_id: str | None = None, before=None, after=None, reason=None) -> None:
    db.session.add(
        AuditEvent(
            tenant_container_id=db.session.get(Company, company_id).tenant_container_id,
            company_id=company_id,
            store_id=store_id,
            actor_user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            before_data=before,
            after_data=after,
        )
    )


def _validated_line(item: dict) -> tuple[str, str | None, int, Decimal]:
    if not isinstance(item, dict):
        raise SalesRuleError("Each order item must be an object.")
    name = str(item.get("name") or "").strip()
    sku = str(item.get("sku") or "").strip() or None
    quantity = _as_integer(item.get("quantity", 0), field="Item quantity")
    if not name or len(name) > 255 or quantity < 1:
        raise SalesRuleError("Item name and a positive whole-number quantity are required.")
    if sku and len(sku) > 128:
        raise SalesRuleError("Item SKU is too long.")
    price = as_money(item.get("unit_price"), field="unit price")
    if price <= 0:
        raise SalesRuleError("Unit price must be greater than zero.")
    if price * quantity >= Decimal("100000000000"):
        raise SalesRuleError("Item total exceeds the supported amount.")
    return name, sku, quantity, price


def _recalculate_order(order: SalesOrder) -> Decimal:
    value = db.session.execute(
        select(func.coalesce(func.sum(SalesOrderLine.line_total), 0)).where(
            SalesOrderLine.tenant_container_id == order.tenant_container_id,
            SalesOrderLine.company_id == order.company_id,
            SalesOrderLine.order_id == order.id,
            SalesOrderLine.is_active.is_(True),
        )
    ).scalar_one()
    order.total_amount = Decimal(str(value or 0)).quantize(MONEY_QUANTUM)
    return Decimal(order.total_amount)


def _issue_invoice(order: SalesOrder, company: Company) -> None:
    methods = set(
        db.session.execute(
            select(OrderPayment.method).where(
                OrderPayment.tenant_container_id == order.tenant_container_id,
                OrderPayment.company_id == order.company_id,
                OrderPayment.order_id == order.id,
            )
        ).scalars()
    )
    if not methods:
        raise SalesRuleError("A paid invoice requires at least one recorded payment.", 409, "payment_required")
    category = next(iter(methods)) if len(methods) == 1 else company.mixed_tender_category
    if category not in {"cash", "bank", "bank_transfer", "other"}:
        raise SalesRuleError("The company's mixed-payment invoice category is invalid.", 409, "mixed_tender_unconfigured")
    series = db.session.execute(
        select(BillingSeries)
        .where(
            BillingSeries.tenant_container_id == company.tenant_container_id,
            BillingSeries.company_id == company.id,
            BillingSeries.category == category,
            BillingSeries.is_active.is_(True),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if series is None:
        raise SalesRuleError(f"The {category} billing series is not configured.", 409, "billing_series_missing")
    number = int(series.next_number)
    invoice_number = f"{series.prefix}{number:06d}"
    duplicate = SalesOrder.query.filter_by(tenant_container_id=company.tenant_container_id, company_id=company.id, invoice_number=invoice_number).first()
    if duplicate is not None:
        raise SalesRuleError("The next invoice number is already in use; correct the series counter before checkout.", 409, "invoice_number_conflict")
    series.next_number = number + 1
    order.invoice_category = category
    order.invoice_number = invoice_number


def create_order(actor: User, *, store_id: str, customer_phone: str, customer_name: str | None = None, items: list[dict] | None = None, company_id: str | None = None) -> SalesOrder:
    company = _company_for_actor(actor, company_id)
    store = _require_assigned_store(actor, store_id, company.id)
    phone_search = normalize_phone(customer_phone)
    customer_phone = customer_phone.strip()
    if len(customer_phone) > 64:
        raise SalesRuleError("Customer phone number is too long.")
    if customer_name is not None and not isinstance(customer_name, str):
        raise SalesRuleError("Customer name must be text.")
    name = (customer_name or "").strip() or None
    if name and len(name) > 160:
        raise SalesRuleError("Customer name is too long.")
    items = items or []
    if not items:
        raise SalesRuleError("Add at least one item to create an open bill.")
    order = SalesOrder(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        origin_store_id=store.id,
        customer_name=name,
        customer_phone=customer_phone.strip(),
        phone_search=phone_search,
        business_date=company_today(company),
        status="open",
        total_amount=ZERO,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(order)
    db.session.flush()
    for item in items:
        item_name, sku, quantity, unit_price = _validated_line(item)
        db.session.add(
            SalesOrderLine(
                tenant_container_id=company.tenant_container_id,
                company_id=company.id,
                order_id=order.id,
                added_store_id=store.id,
                name=item_name,
                sku=sku,
                quantity=quantity,
                unit_price=unit_price,
                line_total=(unit_price * quantity).quantize(MONEY_QUANTUM),
                is_active=True,
                created_by_id=actor.id,
            )
        )
    total = _recalculate_order(order)
    if total <= 0:
        raise SalesRuleError("An open bill must have a positive total.")
    _add_audit(
        company.id,
        actor.id,
        "order.created",
        "sales_order",
        order.id,
        store_id=store.id,
        after={"origin_store_id": store.id, "phone_search": phone_search, "total_amount": format(total, ".3f")},
    )
    db.session.commit()
    return order


def find_open_orders(actor: User, *, store_id: str, phone: str, company_id: str | None = None) -> list[dict]:
    company = _company_for_actor(actor, company_id)
    store = _require_assigned_store(actor, store_id, company.id)
    phone_search = normalize_phone(phone)
    query = SalesOrder.query.filter_by(tenant_container_id=company.tenant_container_id, company_id=company.id, phone_search=phone_search, status="open")
    if not can_view_shared_bill(actor, store.id, company_id=company.id):
        query = query.filter_by(origin_store_id=store.id)
    today = company_today(company)
    orders = query.order_by(
        case((SalesOrder.business_date == today, 0), else_=1),
        SalesOrder.business_date.desc(),
        SalesOrder.created_at.desc(),
    ).all()
    return [order_dict(order) for order in orders]


def add_order_item(actor: User, *, order_id: str, store_id: str, item: dict) -> SalesOrder:
    order, store, company = _order_for_actor(actor, order_id, store_id, lock=True)
    if order.status != "open":
        raise SalesRuleError("Only an open unpaid bill can be changed.", 409, "order_closed")
    name, sku, quantity, unit_price = _validated_line(item)
    old_total = Decimal(order.total_amount)
    line = SalesOrderLine(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        order_id=order.id,
        added_store_id=store.id,
        name=name,
        sku=sku,
        quantity=quantity,
        unit_price=unit_price,
        line_total=(unit_price * quantity).quantize(MONEY_QUANTUM),
        is_active=True,
        created_by_id=actor.id,
    )
    db.session.add(line)
    _recalculate_order(order)
    order.updated_by_id = actor.id
    _add_audit(
        company.id,
        actor.id,
        "order.item_added",
        "sales_order_line",
        line.id,
        store_id=store.id,
        before={"order_total": format(old_total, ".3f")},
        after={"name": name, "quantity": quantity, "unit_price": format(unit_price, ".3f"), "order_total": format(Decimal(order.total_amount), ".3f")},
    )
    db.session.commit()
    return order


def request_item_removal(actor: User, *, order_id: str, store_id: str, line_id: str, quantity: int, reason: str) -> OrderRemovalRequest:
    order, store, company = _order_for_actor(actor, order_id, store_id, lock=True)
    if order.status != "open":
        raise SalesRuleError("Only an open bill can have a removal request.", 409, "order_closed")
    line = SalesOrderLine.query.filter_by(tenant_container_id=company.tenant_container_id, company_id=company.id, order_id=order.id, id=line_id, is_active=True).with_for_update().first()
    if line is None:
        raise SalesRuleError("Order item not found.", 404, "not_found")
    quantity = _as_integer(quantity, field="Removal quantity")
    if quantity > line.quantity:
        raise SalesRuleError("Removal quantity must be between one and the quantity on the bill.")
    if not isinstance(reason, str):
        raise SalesRuleError("A text removal reason is required.")
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise SalesRuleError("A removal reason is required (maximum 500 characters).")
    pending_quantity = db.session.execute(
        select(func.coalesce(func.sum(OrderRemovalRequest.quantity_to_remove), 0)).where(
            OrderRemovalRequest.tenant_container_id == company.tenant_container_id,
            OrderRemovalRequest.company_id == company.id,
            OrderRemovalRequest.line_id == line.id,
            OrderRemovalRequest.status == "pending",
        )
    ).scalar_one()
    if int(pending_quantity or 0) + quantity > line.quantity:
        raise SalesRuleError("Pending removal requests already cover that quantity.", 409, "removal_already_pending")
    request = OrderRemovalRequest(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        order_id=order.id,
        line_id=line.id,
        requesting_store_id=store.id,
        quantity_to_remove=quantity,
        reason=reason,
        status="pending",
        requested_by_id=actor.id,
    )
    db.session.add(request)
    db.session.flush()
    _add_audit(
        company.id,
        actor.id,
        "order.item_removal_requested",
        "order_removal_request",
        request.id,
        store_id=store.id,
        after={"order_id": order.id, "line_id": line.id, "quantity": quantity},
        reason=reason,
    )
    db.session.commit()
    return request


def _can_approve(actor: User, company_id: str, store_id: str, tenant_container_id: str) -> bool:
    if actor.is_super_admin:
        return True
    membership = current_membership(actor, tenant_container_id=tenant_container_id)
    if membership is None or membership.company_id != company_id:
        return False
    if actor.is_company_admin:
        return True
    return actor.effective_role == "manager" and can_access_store(
        actor,
        store_id,
        company_id=company_id,
        tenant_container_id=tenant_container_id,
    )


def review_removal_request(actor: User, *, request_id: str, approve: bool, review_reason: str | None = None) -> OrderRemovalRequest:
    statement = select(OrderRemovalRequest).where(OrderRemovalRequest.id == request_id)
    if not actor.is_super_admin:
        membership = current_membership(actor)
        if membership is None:
            raise SalesRuleError("Removal request not found.", 404, "not_found")
        statement = statement.where(OrderRemovalRequest.tenant_container_id == membership.tenant_container_id)
    removal = db.session.execute(statement.with_for_update()).scalar_one_or_none()
    if removal is None:
        raise SalesRuleError("Removal request not found.", 404, "not_found")
    if removal.status != "pending":
        raise SalesRuleError("This removal request has already been reviewed.", 409, "request_already_reviewed")
    if removal.requested_by_id == actor.id:
        raise SalesRuleError("The requester cannot approve their own removal.", 403, "self_approval_forbidden")
    if not _can_approve(actor, removal.company_id, removal.requesting_store_id, removal.tenant_container_id):
        raise SalesRuleError("Only an authorized manager or administrator for this store can review removals.", 403, "approval_forbidden")
    order = db.session.execute(
        select(SalesOrder).where(
            SalesOrder.tenant_container_id == removal.tenant_container_id,
            SalesOrder.company_id == removal.company_id,
            SalesOrder.id == removal.order_id,
        ).with_for_update()
    ).scalar_one_or_none()
    line = SalesOrderLine.query.filter_by(
        tenant_container_id=removal.tenant_container_id,
        company_id=removal.company_id,
        id=removal.line_id,
        order_id=removal.order_id,
    ).with_for_update().first()
    if order is None or line is None or order.status != "open" or not line.is_active:
        raise SalesRuleError("The bill or item is no longer open for changes.", 409, "order_changed")
    company = _active_company(order.company_id)
    if review_reason is not None and not isinstance(review_reason, str):
        raise SalesRuleError("Review reason must be text.")
    review_reason = (review_reason or "").strip() or None
    removal.reviewed_by_id = actor.id
    removal.review_reason = review_reason
    removal.reviewed_at = datetime.now(timezone.utc)
    if not approve:
        removal.status = "rejected"
        _add_audit(
            removal.company_id,
            actor.id,
            "order.item_removal_rejected",
            "order_removal_request",
            removal.id,
            store_id=removal.requesting_store_id,
            after={"status": "rejected"},
            reason=review_reason or removal.reason,
        )
        db.session.commit()
        return removal

    previous_quantity = line.quantity
    previous_total = Decimal(order.total_amount)
    new_quantity = previous_quantity - removal.quantity_to_remove
    new_line_total = (Decimal(line.unit_price) * new_quantity).quantize(MONEY_QUANTUM)
    if new_quantity == 0:
        line.quantity = 0
        line.line_total = ZERO
        line.is_active = False
        line.removed_at = removal.reviewed_at
        line.removed_by_id = actor.id
        line.removal_reason = removal.reason
    else:
        line.quantity = new_quantity
        line.line_total = new_line_total
    new_total = _recalculate_order(order)
    paid = _paid_amount(order)
    if new_total < paid:
        db.session.rollback()
        raise SalesRuleError("Removal would exceed the amount paid; process a refund/credit before approving it.", 409, "refund_required")
    removal.status = "approved"
    order.updated_by_id = actor.id
    _add_audit(
        company.id,
        actor.id,
        "order.item_removed",
        "sales_order_line",
        line.id,
        store_id=removal.requesting_store_id,
        before={"quantity": previous_quantity, "order_total": format(previous_total, ".3f")},
        after={"quantity": new_quantity, "order_total": format(new_total, ".3f"), "status": "approved"},
        reason=removal.reason,
    )
    if new_total == 0 and paid == 0:
        order.status = "voided"
        order.voided_at = datetime.now(timezone.utc)
        _add_audit(company.id, actor.id, "order.voided", "sales_order", order.id, store_id=removal.requesting_store_id, after={"status": "voided"}, reason=removal.reason)
    elif new_total == paid:
        _issue_invoice(order, company)
        order.status = "closed"
        order.closed_at = datetime.now(timezone.utc)
        _add_audit(company.id, actor.id, "order.closed", "sales_order", order.id, store_id=removal.requesting_store_id, after={"status": "closed", "invoice_number": order.invoice_number})
    db.session.commit()
    return removal


def record_payment(actor: User, *, order_id: str, store_id: str, method: str, amount, idempotency_key: str | None = None, transaction_reference: str | None = None) -> tuple[SalesOrder, OrderPayment, bool]:
    if not isinstance(method, str) or method not in {"cash", "bank", "bank_transfer", "other"}:
        raise SalesRuleError("Choose Cash, Bank, Bank Transfer, or Other as the payment method.")
    if idempotency_key is not None:
        if not isinstance(idempotency_key, str):
            raise SalesRuleError("Idempotency key must be text.")
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise SalesRuleError("Idempotency key must be between 1 and 128 characters.")
    if transaction_reference is not None:
        if not isinstance(transaction_reference, str):
            raise SalesRuleError("Transaction reference must be text.")
        transaction_reference = transaction_reference.strip() or None
        if transaction_reference and len(transaction_reference) > 128:
            raise SalesRuleError("Transaction reference is too long.")
    order, store, company = _order_for_actor(actor, order_id, store_id, lock=True)
    if idempotency_key:
        existing = OrderPayment.query.filter_by(tenant_container_id=order.tenant_container_id, company_id=order.company_id, idempotency_key=idempotency_key).first()
        if existing is not None:
            if existing.order_id != order.id:
                raise SalesRuleError("This idempotency key was already used for another bill.", 409, "idempotency_conflict")
            return order, existing, True
    if order.status != "open":
        raise SalesRuleError("This bill is already closed.", 409, "order_closed")
    payment_amount = as_money(amount, field="payment", allow_zero=False)
    paid_before = _paid_amount(order)
    balance = Decimal(order.total_amount) - paid_before
    if payment_amount > balance:
        raise SalesRuleError("Payment exceeds the outstanding balance.", 409, "overpayment")
    payment = OrderPayment(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        order_id=order.id,
        store_id=store.id,
        method=method,
        amount=payment_amount,
        idempotency_key=idempotency_key or None,
        transaction_reference=transaction_reference or None,
        received_by_id=actor.id,
    )
    db.session.add(payment)
    db.session.flush()
    paid_after = paid_before + payment_amount
    order.updated_by_id = actor.id
    _add_audit(
        company.id,
        actor.id,
        "order.payment_received",
        "order_payment",
        payment.id,
        store_id=store.id,
        after={"order_id": order.id, "method": method, "amount": format(payment_amount, ".3f"), "paid_total": format(paid_after, ".3f")},
    )
    if paid_after == Decimal(order.total_amount):
        _issue_invoice(order, company)
        order.status = "closed"
        order.closed_at = datetime.now(timezone.utc)
        order.updated_by_id = actor.id
        _add_audit(
            company.id,
            actor.id,
            "order.closed",
            "sales_order",
            order.id,
            store_id=store.id,
            after={"status": "closed", "invoice_category": order.invoice_category, "invoice_number": order.invoice_number},
        )
    db.session.commit()
    return order, payment, False


def _expected_collections(company: Company, store_id: str, business_date: date) -> dict[str, Decimal]:
    start, end = _local_day_bounds_utc(company, business_date)
    rows = db.session.execute(
        select(OrderPayment.method, func.coalesce(func.sum(OrderPayment.amount), 0))
        .where(
            OrderPayment.tenant_container_id == company.tenant_container_id,
            OrderPayment.company_id == company.id,
            OrderPayment.store_id == store_id,
            OrderPayment.created_at >= start,
            OrderPayment.created_at < end,
        )
        .group_by(OrderPayment.method)
    ).all()
    totals = {method: Decimal(str(amount or 0)).quantize(MONEY_QUANTUM) for method, amount in rows}
    return {method: totals.get(method, ZERO) for method in ("cash", "bank", "bank_transfer", "other")}


def submit_cashup(
    actor: User,
    *,
    store_id: str,
    business_date: date,
    counted: dict[str, object],
    notes: str | None = None,
    company_id: str | None = None,
) -> DailyCashup:
    if actor.effective_role != "manager" and not actor.is_company_admin and not actor.is_super_admin:
        raise SalesRuleError("Only a manager or administrator can submit a daily collection closeout.", 403, "cashup_forbidden")
    company = _company_for_actor(actor, company_id)
    store = _require_assigned_store(actor, store_id, company.id)
    if not isinstance(business_date, date):
        raise SalesRuleError("Choose a valid business date.")
    if business_date > company_today(company):
        raise SalesRuleError("A future business date cannot be closed.")
    expected = _expected_collections(company, store.id, business_date)
    normalized_counted = {method: as_money(counted.get(method, 0), field=f"counted {method}") for method in expected}
    existing = DailyCashup.query.filter_by(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        store_id=store.id,
        business_date=business_date,
    ).with_for_update().first()
    if existing and existing.status != "rejected":
        raise SalesRuleError("A closeout for this store/date is already pending or approved.", 409, "cashup_exists")
    if existing:
        cashup = existing
        cashup.status = "submitted"
        cashup.submitted_by_id = actor.id
        cashup.reviewed_by_id = None
        cashup.reviewed_at = None
        cashup.review_note = None
        cashup.submitted_at = datetime.now(timezone.utc)
    else:
        cashup = DailyCashup(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            store_id=store.id,
            business_date=business_date,
            submitted_by_id=actor.id,
            status="submitted",
        )
        db.session.add(cashup)
    cashup.expected_cash = expected["cash"]
    cashup.expected_bank = expected["bank"]
    cashup.expected_bank_transfer = expected["bank_transfer"]
    cashup.expected_other = expected["other"]
    cashup.counted_cash = normalized_counted["cash"]
    cashup.counted_bank = normalized_counted["bank"]
    cashup.counted_bank_transfer = normalized_counted["bank_transfer"]
    cashup.counted_other = normalized_counted["other"]
    if notes is not None and not isinstance(notes, str):
        raise SalesRuleError("Closeout notes must be text.")
    cashup.notes = (notes or "").strip()[:2000] or None
    db.session.flush()
    _add_audit(
        company.id,
        actor.id,
        "cashup.submitted",
        "daily_cashup",
        cashup.id,
        store_id=store.id,
        after={
            "business_date": business_date.isoformat(),
            "expected": {key: format(value, ".3f") for key, value in expected.items()},
            "counted": {key: format(value, ".3f") for key, value in normalized_counted.items()},
        },
    )
    db.session.commit()
    return cashup


def review_cashup(actor: User, *, cashup_id: str, approve: bool, note: str | None = None) -> DailyCashup:
    cashup_statement = select(DailyCashup).where(DailyCashup.id == cashup_id)
    if not actor.is_super_admin:
        membership = current_membership(actor)
        if membership is None:
            raise SalesRuleError("Daily closeout not found.", 404, "not_found")
        cashup_statement = cashup_statement.where(DailyCashup.tenant_container_id == membership.tenant_container_id)
    cashup = db.session.execute(cashup_statement.with_for_update()).scalar_one_or_none()
    if cashup is None:
        raise SalesRuleError("Daily closeout not found.", 404, "not_found")
    if not actor.is_super_admin:
        membership = current_membership(actor, tenant_container_id=cashup.tenant_container_id)
        if membership is None or membership.company_id != cashup.company_id:
            raise SalesRuleError("Daily closeout not found.", 404, "not_found")
    if not (actor.is_super_admin or actor.is_company_admin):
        raise SalesRuleError("Only the Main Admin or Company Admin can review a closeout.", 403, "cashup_review_forbidden")
    if cashup.status != "submitted":
        raise SalesRuleError("This closeout is no longer awaiting review.", 409, "cashup_already_reviewed")
    cashup.status = "approved" if approve else "rejected"
    cashup.reviewed_by_id = actor.id
    cashup.reviewed_at = datetime.now(timezone.utc)
    if note is not None and not isinstance(note, str):
        raise SalesRuleError("Review note must be text.")
    cashup.review_note = (note or "").strip()[:500] or None
    _add_audit(
        cashup.company_id,
        actor.id,
        "cashup.approved" if approve else "cashup.rejected",
        "daily_cashup",
        cashup.id,
        store_id=cashup.store_id,
        before={"status": "submitted"},
        after={"status": cashup.status, "review_note": cashup.review_note},
    )
    db.session.commit()
    return cashup
