"""Transactional sales logic and server-side authorization for tenant-shared bills."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, or_, select

from ..auth.store_scope import accessible_store_ids, can_access_store, can_view_shared_bill
from ..auth.tenant_context import current_membership
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import (
    AuditEvent,
    BillingSeries,
    BusinessNumberSeries,
    CatalogProduct,
    CommissionSetting,
    Company,
    DailyCashup,
    DemandNotice,
    DemandNoticeFulfillment,
    GlobalDiscountSetting,
    InventoryBalance,
    InventoryMovement,
    OrderNumberSeries,
    OrderPayment,
    OrderRemovalRequest,
    OrderReturn,
    OrderReturnLine,
    Quotation,
    QuotationLine,
    RealtimeEvent,
    RETURN_KINDS,
    SalesOrder,
    SalesOrderLine,
    Store,
    StoreCredit,
    StoreCreditRedemption,
    TaxSetting,
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


def _require_sales_pos(actor: User) -> None:
    if not actor.has_permission("use_sales_pos"):
        raise SalesRuleError("You are not allowed to use the point of sale.", 403, "permission_denied")


def _require_sales_domain(
    actor: User,
    *,
    tenant_container_id: str,
    domain: str,
    action: str,
    company_id: str,
    store_id: str | None = None,
) -> None:
    if not can_access_data_domain(
        actor,
        tenant_container_id=tenant_container_id,
        domain=domain,
        action=action,
        company_id=company_id,
        store_id=store_id,
    ):
        raise SalesRuleError(
            f"You are not allowed to {action} this {domain.replace('_', ' ')} data.",
            403,
            "permission_denied",
        )


def _allocate_order_number(company: Company) -> str:
    series = db.session.execute(
        select(OrderNumberSeries)
        .where(
            OrderNumberSeries.tenant_container_id == company.tenant_container_id,
            OrderNumberSeries.company_id == company.id,
            OrderNumberSeries.is_active.is_(True),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if series is None:
        raise SalesRuleError("The company's order-number series is not configured.", 409, "order_number_series_missing")
    number = int(series.next_number)
    if number < 1 or number > 2147483647:
        raise SalesRuleError("The order-number series has reached its supported limit.", 409, "order_number_series_exhausted")
    order_number = f"{series.prefix}{number:06d}"
    duplicate = db.session.execute(
        select(SalesOrder.id).where(
            SalesOrder.tenant_container_id == company.tenant_container_id,
            SalesOrder.company_id == company.id,
            SalesOrder.order_number == order_number,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise SalesRuleError("The next order number is already in use; correct the series counter before checkout.", 409, "order_number_conflict")
    series.next_number = number + 1
    return order_number


def _validated_catalog_line(
    actor: User,
    company: Company,
    store: Store,
    item: dict,
    *,
    unit_price_override=None,
) -> tuple[CatalogProduct, int, Decimal]:
    if not isinstance(item, dict):
        raise SalesRuleError("Each order item must be an object.")
    product_id = item.get("product_id")
    if not isinstance(product_id, str) or not product_id.strip() or len(product_id) > 64:
        raise SalesRuleError("Select a product from the authorized catalog.")
    quantity = _as_integer(item.get("quantity", 0), field="Item quantity")
    product = db.session.execute(
        select(CatalogProduct)
        .where(
            CatalogProduct.id == product_id.strip(),
            CatalogProduct.tenant_container_id == company.tenant_container_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if product is None:
        raise SalesRuleError("Product not found.", 404, "not_found")
    if not product.is_active:
        raise SalesRuleError("Archived products cannot be added to a bill.", 409, "product_archived")
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="product_catalog",
        action="view",
        company_id=product.company_id,
        store_id=store.id if product.company_id == store.company_id else None,
    )
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="inventory",
        action="view",
        company_id=store.company_id,
        store_id=store.id,
    )
    if unit_price_override is None:
        if product.price is None:
            raise SalesRuleError("Set a catalog price before selling this product.", 409, "product_price_missing")
        unit_price = Decimal(product.price).quantize(MONEY_QUANTUM)
    else:
        unit_price = as_money(unit_price_override, field="Quoted unit price", allow_zero=False)
    if unit_price <= 0:
        raise SalesRuleError("Unit price must be greater than zero.", 409, "product_price_invalid")
    return product, quantity, unit_price


def _change_sale_inventory(
    actor: User,
    *,
    store: Store,
    product: CatalogProduct,
    quantity_delta: int,
    movement_type: str,
    reason: str,
    required_action: str,
) -> RealtimeEvent:
    _require_sales_domain(
        actor,
        tenant_container_id=store.tenant_container_id,
        domain="inventory",
        action=required_action,
        company_id=store.company_id,
        store_id=store.id,
    )
    balance = db.session.execute(
        select(InventoryBalance)
        .where(
            InventoryBalance.tenant_container_id == store.tenant_container_id,
            InventoryBalance.company_id == store.company_id,
            InventoryBalance.store_id == store.id,
            InventoryBalance.product_owner_company_id == product.company_id,
            InventoryBalance.product_id == product.id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    old_quantity = balance.quantity_on_hand if balance is not None else 0
    new_quantity = old_quantity + quantity_delta
    if new_quantity < 0:
        raise SalesRuleError(
            f"Insufficient stock for {product.name}; only {old_quantity} unit(s) are available.",
            409,
            "insufficient_stock",
        )
    if new_quantity > 2147483647:
        raise SalesRuleError("Stock on hand exceeds the supported quantity range.", 409, "stock_limit")
    if balance is None:
        balance = InventoryBalance(
            tenant_container_id=store.tenant_container_id,
            company_id=store.company_id,
            store_id=store.id,
            product_owner_company_id=product.company_id,
            product_id=product.id,
            quantity_on_hand=new_quantity,
            updated_by_id=actor.id,
        )
        db.session.add(balance)
    else:
        balance.quantity_on_hand = new_quantity
        balance.updated_by_id = actor.id
    movement = InventoryMovement(
        tenant_container_id=store.tenant_container_id,
        company_id=store.company_id,
        store_id=store.id,
        product_owner_company_id=product.company_id,
        product_id=product.id,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        reason=reason[:500],
        actor_user_id=actor.id,
    )
    db.session.add(movement)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=store.tenant_container_id,
            company_id=store.company_id,
            store_id=store.id,
            actor_user_id=actor.id,
            action="inventory.sale_deducted" if movement_type == "sale" else "inventory.sale_returned",
            entity_type="InventoryBalance",
            entity_id=balance.id,
            reason=reason[:500],
            before_data={"quantity_on_hand": old_quantity},
            after_data={
                "quantity_on_hand": new_quantity,
                "product_id": product.id,
                "quantity_delta": quantity_delta,
                "movement_type": movement_type,
            },
        )
    )
    event = RealtimeEvent(
        tenant_container_id=store.tenant_container_id,
        company_id=store.company_id,
        store_id=store.id,
        product_owner_company_id=product.company_id,
        product_id=product.id,
        event_type="inventory.updated",
        payload={
            "product_id": product.id,
            "quantity_on_hand": new_quantity,
            "quantity_delta": quantity_delta,
            "movement_type": movement_type,
            "movement_id": movement.id,
        },
        actor_user_id=actor.id,
    )
    db.session.add(event)
    db.session.flush()
    return event


def _publish_inventory_events(event_ids: list[int]) -> None:
    if not event_ids:
        return
    from ..realtime.service import publish_realtime_event

    for event_id in event_ids:
        publish_realtime_event(event_id)


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
    _require_sales_pos(actor)
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
    _require_sales_domain(
        actor,
        tenant_container_id=order.tenant_container_id,
        domain="open_bills",
        action="view",
        company_id=order.company_id,
        store_id=store.id,
    )
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
    returns = OrderReturn.query.filter_by(
        tenant_container_id=order.tenant_container_id,
        company_id=order.company_id,
        order_id=order.id,
    ).order_by(OrderReturn.created_at.asc()).all()
    returned_quantity_rows = db.session.execute(
        select(OrderReturnLine.sales_order_line_id, func.coalesce(func.sum(OrderReturnLine.quantity), 0))
        .join(
            OrderReturn,
            (OrderReturn.tenant_container_id == OrderReturnLine.tenant_container_id)
            & (OrderReturn.company_id == OrderReturnLine.company_id)
            & (OrderReturn.id == OrderReturnLine.return_id),
        )
        .where(
            OrderReturn.tenant_container_id == order.tenant_container_id,
            OrderReturn.company_id == order.company_id,
            OrderReturn.order_id == order.id,
        )
        .group_by(OrderReturnLine.sales_order_line_id)
    ).all()
    returned_quantities = {line_id: int(quantity or 0) for line_id, quantity in returned_quantity_rows}
    return {
        "id": order.id,
        "company_id": order.company_id,
        "origin_store_id": order.origin_store_id,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "order_number": order.order_number,
        "source_demand_notice_id": order.source_demand_notice_id,
        "source_quotation_id": order.source_quotation_id,
        "business_date": order.business_date.isoformat(),
        "status": order.status,
        "items": [
            {
                "id": line.id,
                "product_id": line.product_id,
                "name": line.name,
                "sku": line.sku,
                "quantity": line.quantity,
                "returned_quantity": returned_quantities.get(line.id, 0),
                "returnable_quantity": max(line.quantity - returned_quantities.get(line.id, 0), 0),
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
        "returns": [
            {
                "id": return_record.id,
                "store_id": return_record.store_id,
                "refund_method": return_record.refund_method,
                "refund_amount": format(Decimal(return_record.refund_amount), ".3f"),
                "reason": return_record.reason,
                "created_at": return_record.created_at.isoformat() if return_record.created_at else None,
            }
            for return_record in returns
        ],
        "subtotal_amount": format(Decimal(order.subtotal_amount or 0), ".3f"),
        "discount_amount": format(Decimal(order.discount_amount or 0), ".3f"),
        "applied_discount_percentage": format(Decimal(order.applied_discount_percentage or 0), ".3f"),
        "applied_global_discount_percentage": format(Decimal(order.applied_global_discount_percentage or 0), ".3f"),
        "taxes": order.taxes or [],
        "total_amount": format(Decimal(order.total_amount), ".3f"),
        "paid_amount": format(paid, ".3f"),
        "balance": format(max(Decimal(order.total_amount) - paid, ZERO), ".3f"),
        "invoice_category": order.invoice_category,
        "invoice_number": order.invoice_number,
        "delivery_status": order.delivery_status,
        "delivery_address": order.delivery_address,
        "storekeeper_notes": order.storekeeper_notes,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "closed_at": order.closed_at.isoformat() if order.closed_at else None,
    }


def _sales_realtime_event(*, company: Company, store: Store, actor: User, event_type: str, payload: dict) -> RealtimeEvent:
    """Stage a minimal, store-scoped sales event in the same business transaction."""
    event = RealtimeEvent(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        store_id=store.id,
        domain="sales",
        event_type=event_type,
        payload=dict(payload),
        actor_user_id=actor.id,
    )
    db.session.add(event)
    db.session.flush()
    return event


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


def _add_order_line(
    actor: User,
    company: Company,
    store: Store,
    order: SalesOrder,
    item: dict,
    *,
    unit_price_override=None,
) -> tuple[SalesOrderLine, RealtimeEvent]:
    product, quantity, unit_price = _validated_catalog_line(
        actor,
        company,
        store,
        item,
        unit_price_override=unit_price_override,
    )
    line_total = (unit_price * quantity).quantize(MONEY_QUANTUM)
    if line_total >= Decimal("100000000000"):
        raise SalesRuleError("Item total exceeds the supported amount.")
    line = SalesOrderLine(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        order_id=order.id,
        product_owner_company_id=product.company_id,
        product_id=product.id,
        added_store_id=store.id,
        name=product.name,
        sku=product.sku,
        quantity=quantity,
        unit_price=unit_price,
        line_total=line_total,
        is_active=True,
        created_by_id=actor.id,
    )
    db.session.add(line)
    db.session.flush()
    event = _change_sale_inventory(
        actor,
        store=store,
        product=product,
        quantity_delta=-quantity,
        movement_type="sale",
        reason=f"Sale {order.order_number}",
        required_action="view",
    )
    return line, event


def _recalculate_order(order: SalesOrder, company: Company | None = None) -> Decimal:
    """Recompute subtotal, discounts, taxes, and the bill total."""
    value = db.session.execute(
        select(func.coalesce(func.sum(SalesOrderLine.line_total), 0)).where(
            SalesOrderLine.tenant_container_id == order.tenant_container_id,
            SalesOrderLine.company_id == order.company_id,
            SalesOrderLine.order_id == order.id,
            SalesOrderLine.is_active.is_(True),
        )
    ).scalar_one()
    subtotal = Decimal(str(value or 0)).quantize(MONEY_QUANTUM)
    order.subtotal_amount = subtotal
    if company is None:
        company = db.session.get(Company, order.company_id)
    manual_pct = Decimal(str(order.applied_discount_percentage or 0))
    global_pct = _effective_global_discount(company, order.business_date)
    order.applied_global_discount_percentage = global_pct
    after_manual = (subtotal * (Decimal("100") - manual_pct) / Decimal("100")).quantize(MONEY_QUANTUM)
    after_global = (after_manual * (Decimal("100") - global_pct) / Decimal("100")).quantize(MONEY_QUANTUM)
    order.discount_amount = (subtotal - after_global).quantize(MONEY_QUANTUM)
    tax_rows: list[dict] = []
    taxed = after_global
    if company is not None:
        for tax in db.session.execute(
            select(TaxSetting).where(
                TaxSetting.tenant_container_id == company.tenant_container_id,
                TaxSetting.company_id == company.id,
                TaxSetting.is_enabled.is_(True),
            ).order_by(TaxSetting.name.asc())
        ).scalars():
            tax_amount = (taxed * Decimal(str(tax.rate)) / Decimal("100")).quantize(MONEY_QUANTUM)
            tax_rows.append({"name": tax.name, "rate": str(tax.rate), "amount": format(tax_amount, ".3f")})
    order.taxes = tax_rows or None
    tax_total = sum((Decimal(row["amount"]) for row in tax_rows), ZERO)
    order.total_amount = (after_global + tax_total).quantize(MONEY_QUANTUM)
    return Decimal(order.total_amount)


def _effective_global_discount(company: Company | None, business_date: date) -> Decimal:
    """Snapshot the dated company-wide discount percentage for a bill."""
    if company is None:
        return ZERO
    setting = db.session.execute(
        select(GlobalDiscountSetting).where(
            GlobalDiscountSetting.tenant_container_id == company.tenant_container_id,
            GlobalDiscountSetting.company_id == company.id,
        )
    ).scalar_one_or_none()
    if setting is None or not setting.is_active:
        return ZERO
    if setting.start_date and business_date < setting.start_date:
        return ZERO
    if setting.end_date and business_date > setting.end_date:
        return ZERO
    return Decimal(str(setting.percentage))


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


def create_order(
    actor: User,
    *,
    store_id: str,
    customer_phone: str,
    customer_name: str | None = None,
    items: list[dict] | None = None,
    company_id: str | None = None,
    source_demand_notice_id: str | None = None,
    source_demand_notice_fulfillment_key: str | None = None,
    source_quotation_id: str | None = None,
    line_price_overrides: list[object] | None = None,
    discount_percentage: object | None = None,
    primary_salesperson_id: str | None = None,
    secondary_salesperson_id: str | None = None,
    delivery_address: str | None = None,
    storekeeper_notes: str | None = None,
    cashier_notes: str | None = None,
    reminder_date: object | None = None,
    reminder_notes: str | None = None,
) -> SalesOrder:
    company = _company_for_actor(actor, company_id)
    store = _require_assigned_store(actor, store_id, company.id)
    _require_sales_pos(actor)
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="open_bills",
        action="add",
        company_id=company.id,
        store_id=store.id,
    )
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="sales",
        action="add",
        company_id=company.id,
        store_id=store.id,
    )
    phone_search = normalize_phone(customer_phone)
    customer_phone = customer_phone.strip()
    if len(customer_phone) > 64:
        raise SalesRuleError("Customer phone number is too long.")
    if customer_name is not None and not isinstance(customer_name, str):
        raise SalesRuleError("Customer name must be text.")
    name = (customer_name or "").strip() or None
    if name and len(name) > 160:
        raise SalesRuleError("Customer name is too long.")
    if not isinstance(items, list) or not items:
        raise SalesRuleError("Add at least one catalog product to create an open bill.")
    if source_demand_notice_id and source_quotation_id:
        raise SalesRuleError("An order can only be converted from one commercial document.")
    if line_price_overrides is not None:
        if source_demand_notice_id is None and source_quotation_id is None:
            raise SalesRuleError("Only an accepted commercial document can provide quoted prices.")
        if not isinstance(line_price_overrides, list) or len(line_price_overrides) != len(items):
            raise SalesRuleError("Quoted prices must match the commercial document lines.")

    source_notice = None
    source_quote = None
    if source_demand_notice_id:
        source_notice = db.session.execute(
            select(DemandNotice)
            .where(
                DemandNotice.id == source_demand_notice_id,
                DemandNotice.tenant_container_id == company.tenant_container_id,
                DemandNotice.company_id == company.id,
                DemandNotice.store_id == store.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if source_notice is None:
            raise SalesRuleError("Demand notice not found.", 404, "not_found")
        if source_notice.status != "open":
            raise SalesRuleError("Only an open demand notice can be converted.", 409, "invalid_state")
        if not source_notice.product_id or len(items) != 1:
            raise SalesRuleError("Link the demand notice to one catalog product before conversion.", 409, "product_link_required")
        requested_quantity = _as_integer(items[0].get("quantity"), field="Item quantity")
        remaining_quantity = source_notice.quantity_requested - source_notice.quantity_fulfilled
        if str(items[0].get("product_id", "")) != source_notice.product_id or requested_quantity > remaining_quantity:
            raise SalesRuleError("The fulfillment order must match the notice product and remaining quantity.", 409, "source_mismatch")
        if requested_quantity <= 0:
            raise SalesRuleError("Fulfillment quantity must be positive.")
        if source_demand_notice_fulfillment_key is not None:
            key = str(source_demand_notice_fulfillment_key).strip()
            if not key or len(key) > 128:
                raise SalesRuleError("A valid fulfillment idempotency key is required.")
        if line_price_overrides is not None:
            expected_price = Decimal(source_notice.agreed_price) if source_notice.agreed_price is not None else None
            if line_price_overrides != [expected_price]:
                raise SalesRuleError("The converted price does not match the demand notice.", 409, "source_mismatch")

    if source_quotation_id:
        source_quote = db.session.execute(
            select(Quotation)
            .where(
                Quotation.id == source_quotation_id,
                Quotation.tenant_container_id == company.tenant_container_id,
                Quotation.company_id == company.id,
                Quotation.store_id == store.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if source_quote is None:
            raise SalesRuleError("Quotation not found.", 404, "not_found")
        if source_quote.status != "accepted":
            raise SalesRuleError("Only an accepted quotation can be converted.", 409, "invalid_state")
        if source_quote.valid_until is not None and source_quote.valid_until < company_today(company):
            raise SalesRuleError("This quotation has expired.", 409, "quotation_expired")
        quote_lines = db.session.execute(
            select(QuotationLine)
            .where(
                QuotationLine.tenant_container_id == company.tenant_container_id,
                QuotationLine.company_id == company.id,
                QuotationLine.quotation_id == source_quote.id,
            )
            .order_by(QuotationLine.created_at.asc(), QuotationLine.id.asc())
        ).scalars().all()
        if (
            not quote_lines
            or len(quote_lines) != len(items)
            or any(line.is_external or not line.product_id for line in quote_lines)
            or [line.product_id for line in quote_lines] != [str(item.get("product_id", "")) for item in items]
            or [line.quantity for line in quote_lines] != [_as_integer(item.get("quantity"), field="Item quantity") for item in items]
        ):
            raise SalesRuleError("The converted order lines must match the accepted quotation.", 409, "source_mismatch")
        if line_price_overrides is None or [Decimal(value) for value in line_price_overrides] != [Decimal(line.unit_price) for line in quote_lines]:
            raise SalesRuleError("The converted prices must match the accepted quotation.", 409, "source_mismatch")

    manual_discount = ZERO
    if discount_percentage not in (None, "", 0, "0"):
        try:
            manual_discount = Decimal(str(discount_percentage))
        except (InvalidOperation, ValueError, TypeError):
            raise SalesRuleError("The discount percentage must be a number.") from None
        if manual_discount < 0 or manual_discount > 100:
            raise SalesRuleError("The discount percentage must be between 0 and 100.")
        _require_sales_domain(
            actor,
            tenant_container_id=company.tenant_container_id,
            domain="sales",
            action="edit",
            company_id=company.id,
            store_id=store.id,
        )

    salesperson_ids = [value for value in (primary_salesperson_id, secondary_salesperson_id) if value]
    if len(set(salesperson_ids)) != len(salesperson_ids):
        raise SalesRuleError("The primary and secondary salespersons must differ.")
    commission_rate = None
    commission_setting = db.session.execute(
        select(CommissionSetting).where(
            CommissionSetting.tenant_container_id == company.tenant_container_id,
            CommissionSetting.company_id == company.id,
            CommissionSetting.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if commission_setting is not None:
        commission_rate = Decimal(str(commission_setting.commission_percentage))
    for salesperson_id in salesperson_ids:
        user = db.session.get(User, salesperson_id)
        if user is None or not user.is_active:
            raise SalesRuleError("The selected salesperson account does not exist.", 404, "not_found")
        if not user.is_super_admin:
            salesperson_membership = current_membership(user, tenant_container_id=company.tenant_container_id)
            if salesperson_membership is None:
                raise SalesRuleError("The selected salesperson is not a member of this tenant.", 403, "tenant_forbidden")

    cleaned_delivery_address = (delivery_address or "").strip()[:2000] or None
    cleaned_reminder_notes = (reminder_notes or "").strip()[:500] or None
    parsed_reminder_date = None
    if reminder_date not in (None, ""):
        if isinstance(reminder_date, datetime):
            parsed_reminder_date = reminder_date.date()
        elif isinstance(reminder_date, date):
            parsed_reminder_date = reminder_date
        else:
            try:
                parsed_reminder_date = date.fromisoformat(str(reminder_date).strip())
            except ValueError:
                raise SalesRuleError("The reminder date must use YYYY-MM-DD format.") from None

    order_number = _allocate_order_number(company)
    order = SalesOrder(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        origin_store_id=store.id,
        customer_name=name,
        customer_phone=customer_phone.strip(),
        phone_search=phone_search,
        order_number=order_number,
        source_demand_notice_id=source_notice.id if source_notice else None,
        source_quotation_id=source_quote.id if source_quote else None,
        applied_discount_percentage=manual_discount,
        primary_salesperson_id=primary_salesperson_id or None,
        secondary_salesperson_id=secondary_salesperson_id or None,
        primary_commission_rate=commission_rate if primary_salesperson_id else None,
        secondary_commission_rate=commission_rate if secondary_salesperson_id else None,
        delivery_address=cleaned_delivery_address,
        storekeeper_notes=(storekeeper_notes or "").strip()[:500] or None,
        cashier_notes=(cashier_notes or "").strip()[:500] or None,
        reminder_date=parsed_reminder_date,
        reminder_notes=cleaned_reminder_notes,
        business_date=company_today(company),
        status="open",
        total_amount=ZERO,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(order)
    db.session.flush()
    event_ids: list[int] = []
    for index, item in enumerate(items):
        override = line_price_overrides[index] if line_price_overrides is not None else None
        _line, event = _add_order_line(
            actor,
            company,
            store,
            order,
            item,
            unit_price_override=override,
        )
        event_ids.append(event.id)
    total = _recalculate_order(order, company)
    if total <= 0:
        raise SalesRuleError("An open bill must have a positive total.")
    credited_deposit = ZERO
    if source_notice is not None:
        already_applied = db.session.execute(select(func.coalesce(func.sum(DemandNoticeFulfillment.deposit_applied), 0)).where(
            DemandNoticeFulfillment.tenant_container_id == company.tenant_container_id,
            DemandNoticeFulfillment.company_id == company.id,
            DemandNoticeFulfillment.notice_id == source_notice.id,
        )).scalar_one()
        deposit_remaining = max(ZERO, Decimal(source_notice.amount_paid or 0) - Decimal(str(already_applied or 0)))
        if deposit_remaining > 0:
            prior_tenders = db.session.execute(select(OrderPayment.method, func.coalesce(func.sum(OrderPayment.amount), 0)).where(
                OrderPayment.tenant_container_id == company.tenant_container_id,
                OrderPayment.company_id == company.id,
                OrderPayment.transaction_reference == f"notice-deposit-credit:{source_notice.id}",
            ).group_by(OrderPayment.method)).all()
            used_by_method = {method: Decimal(str(amount or 0)) for method, amount in prior_tenders}
            original_by_method: dict[str, Decimal] = {}
            for tender in source_notice.payments or []:
                if not isinstance(tender, dict) or tender.get("method") not in {"cash", "bank", "bank_transfer", "other"}:
                    continue
                try:
                    original_amount = Decimal(str(tender.get("amount", "0"))).quantize(MONEY_QUANTUM)
                except (InvalidOperation, ValueError, TypeError):
                    continue
                original_by_method[tender["method"]] = original_by_method.get(tender["method"], ZERO) + original_amount
            for index, method in enumerate(original_by_method):
                available_tender = max(ZERO, original_by_method[method] - used_by_method.get(method, ZERO))
                applied = min(available_tender, deposit_remaining, total - credited_deposit)
                if applied <= 0:
                    continue
                db.session.add(OrderPayment(
                    tenant_container_id=company.tenant_container_id,
                    company_id=company.id,
                    order_id=order.id,
                    store_id=store.id,
                    method=method,
                    amount=applied,
                    idempotency_key=f"notice-deposit:{source_notice.id}:{source_demand_notice_fulfillment_key or order.id}:{index}"[:128],
                    transaction_reference=f"notice-deposit-credit:{source_notice.id}"[:128],
                    received_by_id=actor.id,
                ))
                db.session.flush()
                credited_deposit += applied
                deposit_remaining -= applied
                _add_audit(company.id, actor.id, "commercial.demand_notice.deposit_applied", "sales_order", order.id, store_id=store.id,
                           after={"notice_id": source_notice.id, "method": method, "amount": format(applied, ".3f")})
                if deposit_remaining <= 0 or credited_deposit >= total:
                    break
    if source_notice is not None:
        fulfilled_quantity = _as_integer(items[0].get("quantity"), field="Item quantity")
        source_notice.quantity_fulfilled += fulfilled_quantity
        if source_notice.quantity_fulfilled >= source_notice.quantity_requested:
            source_notice.quantity_fulfilled = source_notice.quantity_requested
            source_notice.status = "converted"
        source_notice.updated_by_id = actor.id
        db.session.add(DemandNoticeFulfillment(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            notice_id=source_notice.id,
            order_id=order.id,
            quantity=fulfilled_quantity,
            deposit_applied=credited_deposit,
            idempotency_key=source_demand_notice_fulfillment_key or f"order:{order.id}",
            fulfilled_by_id=actor.id,
        ))
        if credited_deposit == total:
            _issue_invoice(order, company)
            order.status = "closed"
            order.closed_at = datetime.now(timezone.utc)
    if source_quote is not None:
        source_quote.status = "converted"
        source_quote.updated_by_id = actor.id
        for quote_line in quote_lines:
            quote_line.converted = True
    _add_audit(
        company.id,
        actor.id,
        "order.created",
        "sales_order",
        order.id,
        store_id=store.id,
        after={
            "order_number": order_number,
            "origin_store_id": store.id,
            "phone_search": phone_search,
            "total_amount": format(total, ".3f"),
            "source_demand_notice_id": source_notice.id if source_notice else None,
            "source_quotation_id": source_quote.id if source_quote else None,
        },
    )
    sales_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.order_changed",
        payload={"order_id": order.id, "order_number": order.order_number, "status": order.status, "total_amount": format(total, ".3f"), "balance": format(max(total - _paid_amount(order), ZERO), ".3f")},
    )
    event_ids.append(sales_event.id)
    db.session.commit()
    _publish_inventory_events(event_ids)
    return order


def express_checkout(
    actor: User,
    *,
    store_id: str,
    items: list[dict],
    payments: list[dict],
    idempotency_key: str,
    customer_phone: str,
    customer_name: str | None = None,
    company_id: str | None = None,
) -> tuple[SalesOrder, bool]:
    """Atomic SKU checkout: catalog prices, inventory, tender, invoice, audit."""
    if not actor.has_permission("express_checkout"):
        raise SalesRuleError("Express checkout permission is required.", 403, "permission_denied")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key.strip()) > 128:
        raise SalesRuleError("A checkout idempotency key of 1-128 characters is required.")
    idempotency_key = idempotency_key.strip()
    if not isinstance(items, list) or not items or len(items) > 100:
        raise SalesRuleError("Add 1-100 items to express checkout.")
    if not isinstance(payments, list) or not payments or len(payments) > 10:
        raise SalesRuleError("Provide 1-10 tender payments.")
    phone_search = normalize_phone(customer_phone)
    cleaned_name = (customer_name or "").strip() or None
    if cleaned_name and len(cleaned_name) > 160:
        raise SalesRuleError("Customer name is too long.")
    company = _company_for_actor(actor, company_id)
    store = _require_assigned_store(actor, store_id, company.id)
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="sales",
        action="add",
        company_id=company.id,
        store_id=store.id,
    )
    canonical_request = json.dumps(
        {
            "store_id": store.id,
            "phone": phone_search,
            "name": cleaned_name,
            "items": items,
            "payments": payments,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    existing_order = db.session.execute(
        select(SalesOrder).where(
            SalesOrder.tenant_container_id == company.tenant_container_id,
            SalesOrder.company_id == company.id,
            SalesOrder.checkout_idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing_order is not None:
        if existing_order.checkout_request_hash != request_hash:
            raise SalesRuleError("This checkout key was already used for different items or payment.", 409, "idempotency_conflict")
        return existing_order, True

    normalized_lines: list[dict] = []
    subtotal = ZERO
    for raw in items:
        if not isinstance(raw, dict):
            raise SalesRuleError("Each checkout item must include SKU and quantity.")
        sku = str(raw.get("sku", "")).strip()
        if not sku or len(sku) > 128:
            raise SalesRuleError("Each checkout item needs a valid SKU.")
        quantity = _as_integer(raw.get("quantity"), field="Item quantity")
        product = db.session.execute(
            select(CatalogProduct)
            .where(
                CatalogProduct.tenant_container_id == company.tenant_container_id,
                CatalogProduct.company_id == company.id,
                CatalogProduct.sku == sku,
                CatalogProduct.is_active.is_(True),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if product is None:
            raise SalesRuleError(f"No active product with SKU {sku} was found.", 404, "product_not_found")
        if product.price is None:
            raise SalesRuleError(f"Set a catalog price for {product.name} before checkout.", 409, "product_price_missing")
        price = Decimal(str(product.price)).quantize(MONEY_QUANTUM)
        normalized_lines.append({"product_id": product.id, "quantity": quantity})
        subtotal += price * quantity
    if len({line["product_id"] for line in normalized_lines}) != len(normalized_lines):
        raise SalesRuleError("Each product may appear only once in express checkout.")

    order = SalesOrder(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        origin_store_id=store.id,
        customer_name=cleaned_name,
        customer_phone=customer_phone.strip()[:64],
        phone_search=phone_search,
        order_number=_allocate_order_number(company),
        checkout_idempotency_key=idempotency_key,
        checkout_request_hash=request_hash,
        business_date=company_today(company),
        status="open",
        total_amount=ZERO,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(order)
    db.session.flush()
    event_ids: list[int] = []
    for item in normalized_lines:
        _line, event = _add_order_line(actor, company, store, order, item)
        event_ids.append(event.id)
    total = _recalculate_order(order, company)
    normalized_payments: list[tuple[str, Decimal, str | None]] = []
    payment_total = ZERO
    for payment in payments:
        if not isinstance(payment, dict):
            raise SalesRuleError("Each tender must include method and amount.")
        method = payment.get("method")
        if method not in {"cash", "bank", "bank_transfer", "other"}:
            raise SalesRuleError("Choose Cash, Bank, Bank Transfer, or Other as a tender.")
        amount = as_money(payment.get("amount"), field="Payment", allow_zero=False)
        reference = payment.get("transaction_reference")
        if reference is not None:
            if not isinstance(reference, str) or len(reference.strip()) > 128:
                raise SalesRuleError("Payment transaction reference must be at most 128 characters.")
            reference = reference.strip() or None
        normalized_payments.append((method, amount, reference))
        payment_total += amount
    if payment_total != total:
        raise SalesRuleError("Express checkout payments must exactly match the bill total.", 409, "payment_total_mismatch")
    for index, (method, amount, reference) in enumerate(normalized_payments):
        db.session.add(
            OrderPayment(
                tenant_container_id=company.tenant_container_id,
                company_id=company.id,
                order_id=order.id,
                store_id=store.id,
                method=method,
                amount=amount,
                idempotency_key=f"express:{idempotency_key}:{index}",
                transaction_reference=reference,
                received_by_id=actor.id,
            )
        )
    db.session.flush()
    _issue_invoice(order, company)
    order.status = "closed"
    order.closed_at = datetime.now(timezone.utc)
    order.updated_by_id = actor.id
    _add_audit(
        company.id,
        actor.id,
        "order.express_checkout_completed",
        "sales_order",
        order.id,
        store_id=store.id,
        after={
            "order_number": order.order_number,
            "invoice_number": order.invoice_number,
            "total": format(total, ".3f"),
            "items": len(normalized_lines),
            "payments": len(normalized_payments),
        },
    )
    sales_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.order_changed",
        payload={"order_id": order.id, "order_number": order.order_number, "status": order.status, "total_amount": format(total, ".3f"), "balance": "0.000"},
    )
    event_ids.append(sales_event.id)
    db.session.commit()
    _publish_inventory_events(event_ids)
    return order, False


def find_open_orders(actor: User, *, store_id: str, phone: str, company_id: str | None = None) -> list[dict]:
    company = _company_for_actor(actor, company_id)
    store = _require_assigned_store(actor, store_id, company.id)
    _require_sales_pos(actor)
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="open_bills",
        action="view",
        company_id=company.id,
        store_id=store.id,
    )
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


def find_returnable_orders(
    actor: User,
    *,
    store_id: str,
    search: str,
    company_id: str | None = None,
) -> list[dict]:
    company = _company_for_actor(actor, company_id)
    store = _require_assigned_store(actor, store_id, company.id)
    _require_sales_pos(actor)
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="sales",
        action="view",
        company_id=company.id,
        store_id=store.id,
    )
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="open_bills",
        action="view",
        company_id=company.id,
        store_id=store.id,
    )
    value = str(search or "").strip()[:80]
    if not value:
        raise SalesRuleError("Enter an order reference, invoice number, or customer phone.")
    criteria = [
        func.upper(SalesOrder.order_number) == value.upper(),
        func.upper(SalesOrder.invoice_number) == value.upper(),
    ]
    try:
        criteria.append(SalesOrder.phone_search == normalize_phone(value))
    except SalesRuleError:
        pass
    query = SalesOrder.query.filter(
        SalesOrder.tenant_container_id == company.tenant_container_id,
        SalesOrder.company_id == company.id,
        SalesOrder.status == "closed",
        or_(*criteria),
    )
    if not can_view_shared_bill(
        actor,
        store.id,
        company_id=company.id,
        tenant_container_id=company.tenant_container_id,
    ):
        query = query.filter(SalesOrder.origin_store_id == store.id)
    orders = query.order_by(SalesOrder.closed_at.desc(), SalesOrder.id.asc()).limit(50).all()
    return [order_dict(order) for order in orders]


def add_order_item(actor: User, *, order_id: str, store_id: str, item: dict) -> SalesOrder:
    order, store, company = _order_for_actor(actor, order_id, store_id, lock=True)
    if order.status != "open":
        raise SalesRuleError("Only an open bill can be changed.", 409, "order_closed")
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="open_bills",
        action="add",
        company_id=company.id,
        store_id=store.id,
    )
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="sales",
        action="add",
        company_id=company.id,
        store_id=store.id,
    )
    old_total = Decimal(order.total_amount)
    line, event = _add_order_line(actor, company, store, order, item)
    new_total = _recalculate_order(order, company)
    order.updated_by_id = actor.id
    _add_audit(
        company.id,
        actor.id,
        "order.item_added",
        "sales_order_line",
        line.id,
        store_id=store.id,
        before={"order_total": format(old_total, ".3f")},
        after={
            "product_id": line.product_id,
            "name": line.name,
            "quantity": line.quantity,
            "unit_price": format(Decimal(line.unit_price), ".3f"),
            "order_total": format(new_total, ".3f"),
        },
    )
    sales_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.order_changed",
        payload={"order_id": order.id, "order_number": order.order_number, "status": order.status, "total_amount": format(new_total, ".3f"), "balance": format(max(new_total - _paid_amount(order), ZERO), ".3f")},
    )
    db.session.commit()
    _publish_inventory_events([event.id, sales_event.id])
    return order


def request_item_removal(actor: User, *, order_id: str, store_id: str, line_id: str, quantity: int, reason: str) -> OrderRemovalRequest:
    order, store, company = _order_for_actor(actor, order_id, store_id, lock=True)
    if order.status != "open":
        raise SalesRuleError("Only an open bill can have a removal request.", 409, "order_closed")
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="open_bills",
        action="edit",
        company_id=company.id,
        store_id=store.id,
    )
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
    realtime_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.removal_changed",
        payload={"order_id": order.id, "request_id": request.id, "status": "pending"},
    )
    db.session.commit()
    _publish_inventory_events([realtime_event.id])
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
    _require_sales_domain(
        actor,
        tenant_container_id=removal.tenant_container_id,
        domain="open_bills",
        action="edit",
        company_id=removal.company_id,
        store_id=removal.requesting_store_id,
    )
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
        removal_store = _store_for_company(removal.requesting_store_id, removal.company_id)
        realtime_event = _sales_realtime_event(
            company=company,
            store=removal_store,
            actor=actor,
            event_type="sales.removal_changed",
            payload={"order_id": order.id, "request_id": removal.id, "status": "rejected"},
        )
        db.session.commit()
        _publish_inventory_events([realtime_event.id])
        return removal

    previous_quantity = line.quantity
    previous_total = Decimal(order.total_amount)
    new_quantity = previous_quantity - removal.quantity_to_remove
    new_line_total = (Decimal(line.unit_price) * new_quantity).quantize(MONEY_QUANTUM)
    inventory_event_ids: list[int] = []
    if line.product_id and line.product_owner_company_id:
        product = db.session.execute(
            select(CatalogProduct).where(
                CatalogProduct.id == line.product_id,
                CatalogProduct.company_id == line.product_owner_company_id,
                CatalogProduct.tenant_container_id == removal.tenant_container_id,
            )
        ).scalar_one_or_none()
        if product is None:
            raise SalesRuleError("The catalog product linked to this bill item no longer exists.", 409, "product_missing")
        return_store = _store_for_company(removal.requesting_store_id, removal.company_id)
        inventory_event = _change_sale_inventory(
            actor,
            store=return_store,
            product=product,
            quantity_delta=removal.quantity_to_remove,
            movement_type="return",
            reason=f"Approved return for {order.order_number}: {removal.reason}",
            required_action="add",
        )
        inventory_event_ids.append(inventory_event.id)
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
    new_total = _recalculate_order(order, company)
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
    realtime_event = _sales_realtime_event(
        company=company,
        store=_store_for_company(removal.requesting_store_id, removal.company_id),
        actor=actor,
        event_type="sales.removal_changed",
        payload={"order_id": order.id, "request_id": removal.id, "status": removal.status},
    )
    inventory_event_ids.append(realtime_event.id)
    db.session.commit()
    _publish_inventory_events(inventory_event_ids)
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
    _require_sales_domain(
        actor,
        tenant_container_id=order.tenant_container_id,
        domain="sales",
        action="add",
        company_id=order.company_id,
        store_id=store.id,
    )
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
    realtime_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.payment_recorded",
        payload={
            "order_id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": format(Decimal(order.total_amount), ".3f"),
            "paid_amount": format(paid_after, ".3f"),
            "balance": format(Decimal(order.total_amount) - paid_after, ".3f"),
        },
    )
    db.session.commit()
    _publish_inventory_events([realtime_event.id])
    return order, payment, False


def find_store_credits(actor: User, *, phone: str, company_id: str | None = None) -> list[StoreCredit]:
    company = _company_for_actor(actor, company_id)
    phone_search = normalize_phone(phone)
    _require_sales_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="view", company_id=company.id)
    rows = db.session.execute(
        select(StoreCredit).where(
            StoreCredit.tenant_container_id == company.tenant_container_id,
            StoreCredit.company_id == company.id,
            StoreCredit.phone_search == phone_search,
            StoreCredit.status == "open",
            StoreCredit.remaining_amount > 0,
        ).order_by(StoreCredit.created_at.desc()).limit(100)
    ).scalars()
    now = datetime.now(timezone.utc)
    active: list[StoreCredit] = []
    for credit in rows:
        expires_at = credit.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is None or expires_at > now:
            active.append(credit)
        if len(active) >= 50:
            break
    return active


def redeem_store_credit(
    actor: User,
    *,
    credit_id: str,
    order_id: str,
    store_id: str,
    customer_phone: str,
    amount,
    idempotency_key: str,
) -> tuple[SalesOrder, StoreCreditRedemption, bool]:
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key.strip()) > 128:
        raise SalesRuleError("A store-credit redemption key of 1-128 characters is required.")
    key = idempotency_key.strip()
    phone_search = normalize_phone(customer_phone)
    order, store, company = _order_for_actor(actor, order_id, store_id, lock=True)
    _require_sales_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="add", company_id=company.id, store_id=store.id)
    credit = db.session.execute(
        select(StoreCredit).where(
            StoreCredit.tenant_container_id == company.tenant_container_id,
            StoreCredit.company_id == company.id,
            StoreCredit.id == credit_id,
        ).with_for_update()
    ).scalar_one_or_none()
    if credit is None:
        raise SalesRuleError("Store credit not found.", 404, "credit_not_found")
    if credit.phone_search != phone_search or order.phone_search != phone_search:
        raise SalesRuleError("Customer phone must match both the credit and the bill.", 403, "credit_customer_mismatch")
    existing = db.session.execute(
        select(StoreCreditRedemption).where(
            StoreCreditRedemption.tenant_container_id == company.tenant_container_id,
            StoreCreditRedemption.company_id == company.id,
            StoreCreditRedemption.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.store_credit_id != credit_id or existing.order_id != order.id or Decimal(existing.amount) != as_money(amount, field="Credit redemption", allow_zero=False):
            raise SalesRuleError("This redemption key was already used for another credit or amount.", 409, "idempotency_conflict")
        return order, existing, True
    if order.status != "open":
        raise SalesRuleError("Store credit can only be applied to an open bill.", 409, "order_closed")
    now = datetime.now(timezone.utc)
    if credit.status != "open" or Decimal(credit.remaining_amount) <= ZERO:
        raise SalesRuleError("This store credit has no remaining value.", 409, "credit_unavailable")
    if credit.expires_at is not None:
        expires_at = credit.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise SalesRuleError("This store credit has expired.", 409, "credit_expired")
    credit_amount = as_money(amount, field="Credit redemption", allow_zero=False)
    paid_before = _paid_amount(order)
    outstanding = Decimal(order.total_amount) - paid_before
    if credit_amount > Decimal(credit.remaining_amount) or credit_amount > outstanding:
        raise SalesRuleError("Credit redemption exceeds either the remaining credit or bill balance.", 409, "credit_amount_exceeded")
    payment = OrderPayment(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        order_id=order.id,
        store_id=store.id,
        method="other",
        amount=credit_amount,
        idempotency_key=f"store-credit:{hashlib.sha256(key.encode('utf-8')).hexdigest()}",
        transaction_reference=f"Store credit {credit.credit_number}",
        received_by_id=actor.id,
    )
    db.session.add(payment)
    db.session.flush()
    redemption = StoreCreditRedemption(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        store_credit_id=credit.id,
        order_id=order.id,
        payment_id=payment.id,
        amount=credit_amount,
        idempotency_key=key,
        processed_by_id=actor.id,
    )
    db.session.add(redemption)
    credit.remaining_amount = Decimal(credit.remaining_amount) - credit_amount
    if credit.remaining_amount == ZERO:
        credit.status = "fully_used"
    paid_after = paid_before + credit_amount
    order.updated_by_id = actor.id
    _add_audit(company.id, actor.id, "store_credit.redeemed", "store_credit", credit.id, store_id=store.id, before={"remaining_amount": format(Decimal(credit.remaining_amount) + credit_amount, ".3f")}, after={"remaining_amount": format(credit.remaining_amount, ".3f"), "order_id": order.id, "amount": format(credit_amount, ".3f")})
    if paid_after == Decimal(order.total_amount):
        _issue_invoice(order, company)
        order.status = "closed"
        order.closed_at = now
        _add_audit(company.id, actor.id, "order.closed", "sales_order", order.id, store_id=store.id, after={"status": "closed", "invoice_number": order.invoice_number})
    realtime_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.payment_recorded",
        payload={
            "order_id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": format(Decimal(order.total_amount), ".3f"),
            "paid_amount": format(paid_after, ".3f"),
            "balance": format(Decimal(order.total_amount) - paid_after, ".3f"),
        },
    )
    db.session.commit()
    _publish_inventory_events([realtime_event.id])
    return order, redemption, False


def _allocate_credit_number(company: Company) -> str:
    locked_company = db.session.execute(
        select(Company).where(
            Company.id == company.id,
            Company.tenant_container_id == company.tenant_container_id,
        ).with_for_update()
    ).scalar_one_or_none()
    if locked_company is None or not locked_company.is_active:
        raise SalesRuleError("Company not found.", 404, "not_found")
    series = db.session.execute(
        select(BusinessNumberSeries).where(
            BusinessNumberSeries.tenant_container_id == company.tenant_container_id,
            BusinessNumberSeries.company_id == company.id,
            BusinessNumberSeries.document_type == "store_credit",
        ).with_for_update()
    ).scalar_one_or_none()
    if series is None:
        series = BusinessNumberSeries(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            document_type="store_credit",
            prefix="CR-",
            next_number=1,
        )
        db.session.add(series)
        db.session.flush()
    number = int(series.next_number)
    if number <= 0 or number > 999999999:
        raise SalesRuleError("Store credit number series is exhausted; contact an administrator.", 409, "series_exhausted")
    series.next_number = number + 1
    return f"{series.prefix}{number:06d}"


def _issue_store_credit(
    actor: User,
    *,
    company: Company,
    order: SalesOrder,
    return_record: OrderReturn,
    amount: Decimal,
    customer_name: str | None,
    customer_phone: str,
) -> StoreCredit:
    credit = StoreCredit(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        credit_number=_allocate_credit_number(company),
        customer_name=customer_name,
        customer_phone=customer_phone,
        phone_search=normalize_phone(customer_phone),
        amount=amount,
        remaining_amount=amount,
        status="open",
        source_order_id=order.id,
        source_return_id=return_record.id,
        issued_by_id=actor.id,
        reason=return_record.reason,
    )
    db.session.add(credit)
    db.session.flush()
    _add_audit(
        company.id,
        actor.id,
        "sales.store_credit.issued",
        "store_credit",
        credit.id,
        store_id=return_record.store_id,
        after={
            "credit_number": credit.credit_number,
            "amount": format(amount, ".3f"),
            "customer_phone": credit.phone_search,
            "source_order": order.order_number,
        },
    )
    return credit


def _build_exchange_order(
    actor: User,
    *,
    company: Company,
    store: Store,
    source_order: SalesOrder,
    return_record: OrderReturn,
    exchange_items: list[dict] | None,
    customer_name: str | None,
    customer_phone: str,
) -> tuple[SalesOrder, list[int]]:
    if not isinstance(exchange_items, list) or not exchange_items or len(exchange_items) > 100:
        raise SalesRuleError("An exchange needs 1-100 replacement items.")
    order_number = _allocate_order_number(company)
    exchange_order = SalesOrder(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        origin_store_id=store.id,
        customer_name=(customer_name or "").strip() or None,
        customer_phone=customer_phone.strip(),
        phone_search=normalize_phone(customer_phone),
        order_number=order_number,
        source_return_id=return_record.id,
        business_date=company_today(company),
        status="open",
        total_amount=ZERO,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(exchange_order)
    db.session.flush()
    event_ids: list[int] = []
    for item in exchange_items:
        _line, event = _add_order_line(actor, company, store, exchange_order, item)
        event_ids.append(event.id)
    total = _recalculate_order(exchange_order, company)
    if total <= 0:
        raise SalesRuleError("An exchange bill must have a positive total.")
    credit_applied = min(Decimal(return_record.refund_amount), total)
    if credit_applied > 0:
        payment = OrderPayment(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            order_id=exchange_order.id,
            store_id=store.id,
            method="other",
            amount=credit_applied,
            idempotency_key=f"exchange:{return_record.id}",
            transaction_reference=f"Exchange for {source_order.order_number}",
            received_by_id=actor.id,
        )
        db.session.add(payment)
        db.session.flush()
        if credit_applied == total:
            _issue_invoice(exchange_order, company)
            exchange_order.status = "closed"
            exchange_order.closed_at = datetime.now(timezone.utc)
    surplus_credit = Decimal(return_record.refund_amount) - credit_applied
    if surplus_credit > 0:
        _issue_store_credit(
            actor,
            company=company,
            order=source_order,
            return_record=return_record,
            amount=surplus_credit,
            customer_name=source_order.customer_name,
            customer_phone=source_order.customer_phone,
        )
    _add_audit(
        company.id,
        actor.id,
        "order.exchange_created",
        "sales_order",
        exchange_order.id,
        store_id=store.id,
        after={
            "order_number": order_number,
            "source_order": source_order.order_number,
            "total_amount": format(total, ".3f"),
            "credit_applied": format(credit_applied, ".3f"),
            "store_credit_issued": format(surplus_credit, ".3f"),
        },
    )
    return exchange_order, event_ids


def process_order_return(
    actor: User,
    *,
    order_id: str,
    store_id: str,
    items: list[dict],
    reason: str,
    refund_method: str,
    idempotency_key: str,
    transaction_reference: str | None = None,
    kind: str = "refund",
    exchange_items: list[dict] | None = None,
    customer_name: str | None = None,
) -> tuple[SalesOrder, OrderReturn, bool]:
    """Return sold quantities, restore stock, and refund, exchange, or credit."""
    if not (actor.is_super_admin or actor.is_company_admin or actor.effective_role == "manager"):
        raise SalesRuleError("Only a manager or administrator can process a return/refund.", 403, "return_forbidden")
    if kind not in RETURN_KINDS:
        raise SalesRuleError("Choose refund, exchange, or store credit.")
    if kind != "refund":
        refund_method = "other"
    if not isinstance(refund_method, str) or refund_method not in {"cash", "bank", "bank_transfer", "other"}:
        raise SalesRuleError("Choose the tender used to issue the refund.")
    if not isinstance(idempotency_key, str):
        raise SalesRuleError("A refund idempotency key is required.")
    idempotency_key = idempotency_key.strip()
    if not idempotency_key or len(idempotency_key) > 128:
        raise SalesRuleError("Refund idempotency key must be between 1 and 128 characters.")
    if transaction_reference is not None:
        if not isinstance(transaction_reference, str):
            raise SalesRuleError("Refund transaction reference must be text.")
        transaction_reference = transaction_reference.strip() or None
        if transaction_reference and len(transaction_reference) > 128:
            raise SalesRuleError("Refund transaction reference is too long.")
    if not isinstance(reason, str):
        raise SalesRuleError("A return/refund reason is required.")
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise SalesRuleError("A return/refund reason is required (maximum 500 characters).")
    if not isinstance(items, list) or not items or len(items) > 100:
        raise SalesRuleError("Select between one and 100 order lines to return.")

    requested_quantities: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            raise SalesRuleError("Each returned item must identify an order line and quantity.")
        line_id = item.get("line_id")
        if not isinstance(line_id, str) or not line_id.strip() or len(line_id) > 64:
            raise SalesRuleError("Each returned item must identify an order line.")
        line_id = line_id.strip()
        if line_id in requested_quantities:
            raise SalesRuleError("An order line may appear only once in a return.")
        requested_quantities[line_id] = _as_integer(item.get("quantity"), field="Return quantity")

    order, store, company = _order_for_actor(actor, order_id, store_id, lock=True)
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="sales",
        action="edit",
        company_id=company.id,
        store_id=store.id,
    )
    if order.status != "closed":
        raise SalesRuleError("Only a fully settled bill can be returned/refunded.", 409, "order_not_settled")

    existing_return = db.session.execute(
        select(OrderReturn)
        .where(
            OrderReturn.tenant_container_id == company.tenant_container_id,
            OrderReturn.company_id == company.id,
            OrderReturn.idempotency_key == idempotency_key,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if existing_return is not None:
        existing_lines = db.session.execute(
            select(OrderReturnLine.sales_order_line_id, OrderReturnLine.quantity).where(
                OrderReturnLine.tenant_container_id == company.tenant_container_id,
                OrderReturnLine.company_id == company.id,
                OrderReturnLine.return_id == existing_return.id,
            )
        ).all()
        if (
            existing_return.order_id != order.id
            or existing_return.kind != kind
            or existing_return.store_id != store.id
            or existing_return.refund_method != refund_method
            or existing_return.reason != reason
            or existing_return.transaction_reference != transaction_reference
            or {line_id: quantity for line_id, quantity in existing_lines} != requested_quantities
        ):
            raise SalesRuleError("This idempotency key was already used for a different return/refund.", 409, "idempotency_conflict")
        return order, existing_return, True

    lines = list(
        db.session.execute(
            select(SalesOrderLine)
            .where(
                SalesOrderLine.tenant_container_id == company.tenant_container_id,
                SalesOrderLine.company_id == company.id,
                SalesOrderLine.order_id == order.id,
                SalesOrderLine.id.in_(list(requested_quantities)),
                SalesOrderLine.is_active.is_(True),
            )
            .order_by(SalesOrderLine.id.asc())
            .with_for_update()
        ).scalars()
    )
    line_by_id = {line.id: line for line in lines}
    if set(line_by_id) != set(requested_quantities):
        raise SalesRuleError("One or more order items are not available for return.", 404, "return_line_not_found")

    prior_rows = db.session.execute(
        select(
            OrderReturnLine.sales_order_line_id,
            func.coalesce(func.sum(OrderReturnLine.quantity), 0),
            func.coalesce(func.sum(OrderReturnLine.line_total), 0),
        )
        .join(
            OrderReturn,
            (OrderReturn.tenant_container_id == OrderReturnLine.tenant_container_id)
            & (OrderReturn.company_id == OrderReturnLine.company_id)
            & (OrderReturn.id == OrderReturnLine.return_id),
        )
        .where(
            OrderReturn.tenant_container_id == company.tenant_container_id,
            OrderReturn.company_id == company.id,
            OrderReturn.order_id == order.id,
            OrderReturnLine.sales_order_line_id.in_(list(requested_quantities)),
        )
        .group_by(OrderReturnLine.sales_order_line_id)
    ).all()
    previously_returned = {line_id: int(quantity or 0) for line_id, quantity, _amount in prior_rows}
    previously_refunded_amounts = {line_id: Decimal(str(amount or 0)).quantize(MONEY_QUANTUM) for line_id, _quantity, amount in prior_rows}
    all_order_lines = list(db.session.execute(
        select(SalesOrderLine).where(
            SalesOrderLine.tenant_container_id == company.tenant_container_id,
            SalesOrderLine.company_id == company.id,
            SalesOrderLine.order_id == order.id,
            SalesOrderLine.is_active.is_(True),
        ).order_by(SalesOrderLine.id.asc())
    ).scalars())
    subtotal = Decimal(order.subtotal_amount or 0)
    effective_total = Decimal(order.total_amount or 0)
    if subtotal <= ZERO:
        raise SalesRuleError("The original bill does not contain a refundable subtotal.", 409, "invalid_refund_basis")
    line_refund_targets: dict[str, Decimal] = {}
    allocated = ZERO
    for historical_line in all_order_lines:
        target = (Decimal(historical_line.line_total) * effective_total / subtotal).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        line_refund_targets[historical_line.id] = target
        allocated += target
    if all_order_lines:
        last_line_id = all_order_lines[-1].id
        line_refund_targets[last_line_id] += effective_total - allocated

    line_amounts: dict[str, Decimal] = {}
    total_refund = ZERO
    for line_id, quantity in requested_quantities.items():
        line = line_by_id[line_id]
        returned_before = previously_returned.get(line_id, 0)
        returnable = line.quantity - returned_before
        if quantity > returnable:
            raise SalesRuleError(
                f"Cannot return more {line.name} than the remaining returnable quantity ({max(returnable, 0)}).",
                409,
                "return_quantity_exceeded",
            )
        cumulative_quantity = returned_before + quantity
        cumulative_amount = (line_refund_targets[line_id] * cumulative_quantity / line.quantity).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        amount = cumulative_amount - previously_refunded_amounts.get(line_id, ZERO)
        if amount < ZERO:
            raise SalesRuleError("The refund allocation is inconsistent with prior returns.", 409, "refund_allocation_conflict")
        line_amounts[line_id] = amount
        total_refund += amount
    total_refund = total_refund.quantize(MONEY_QUANTUM)
    if total_refund <= ZERO:
        raise SalesRuleError("The returned items must have a positive refund value.")
    paid_amount = _paid_amount(order)
    previously_refunded = db.session.execute(
        select(func.coalesce(func.sum(OrderReturn.refund_amount), 0)).where(
            OrderReturn.tenant_container_id == company.tenant_container_id,
            OrderReturn.company_id == company.id,
            OrderReturn.order_id == order.id,
        )
    ).scalar_one()
    refundable_remaining = paid_amount - Decimal(str(previously_refunded or 0)).quantize(MONEY_QUANTUM)
    if total_refund > refundable_remaining:
        raise SalesRuleError("Refund would exceed the remaining amount paid on this bill.", 409, "refund_exceeds_paid")

    return_record = OrderReturn(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        order_id=order.id,
        store_id=store.id,
        kind=kind,
        refund_method=refund_method,
        refund_amount=total_refund,
        idempotency_key=idempotency_key,
        reason=reason,
        transaction_reference=transaction_reference,
        processed_by_id=actor.id,
    )
    db.session.add(return_record)
    db.session.flush()
    inventory_event_ids: list[int] = []
    exchange_order = None
    if kind == "exchange":
        exchange_order, exchange_event_ids = _build_exchange_order(
            actor,
            company=company,
            store=store,
            source_order=order,
            return_record=return_record,
            exchange_items=exchange_items,
            customer_name=customer_name or order.customer_name,
            customer_phone=order.customer_phone,
        )
        return_record.exchange_order_id = exchange_order.id
        inventory_event_ids.extend(exchange_event_ids)
        db.session.flush()
    elif kind == "store_credit":
        _issue_store_credit(
            actor,
            company=company,
            order=order,
            return_record=return_record,
            amount=total_refund,
            customer_name=customer_name or order.customer_name,
            customer_phone=order.customer_phone,
        )
    for line_id, quantity in requested_quantities.items():
        line = line_by_id[line_id]
        db.session.add(
            OrderReturnLine(
                tenant_container_id=company.tenant_container_id,
                company_id=company.id,
                return_id=return_record.id,
                sales_order_line_id=line.id,
                quantity=quantity,
                unit_price=line.unit_price,
                line_total=line_amounts[line_id],
            )
        )
        if line.product_id and line.product_owner_company_id:
            product = db.session.execute(
                select(CatalogProduct)
                .where(
                    CatalogProduct.tenant_container_id == company.tenant_container_id,
                    CatalogProduct.company_id == line.product_owner_company_id,
                    CatalogProduct.id == line.product_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if product is None:
                raise SalesRuleError("A returned catalog product no longer exists.", 409, "product_missing")
            _require_sales_domain(
                actor,
                tenant_container_id=company.tenant_container_id,
                domain="product_catalog",
                action="view",
                company_id=product.company_id,
                store_id=store.id if product.company_id == store.company_id else None,
            )
            inventory_event = _change_sale_inventory(
                actor,
                store=store,
                product=product,
                quantity_delta=quantity,
                movement_type="return",
                reason=f"Refund {order.order_number}: {reason}",
                required_action="add",
            )
            inventory_event_ids.append(inventory_event.id)
    db.session.flush()
    _add_audit(
        company.id,
        actor.id,
        "sales.return_refunded" if kind == "refund" else f"sales.return_{kind}",
        "order_return",
        return_record.id,
        store_id=store.id,
        after={
            "order_id": order.id,
            "order_number": order.order_number,
            "kind": return_record.kind,
            "refund_method": refund_method,
            "refund_amount": format(total_refund, ".3f"),
            "items": [
                {"line_id": line_id, "quantity": quantity, "amount": format(line_amounts[line_id], ".3f")}
                for line_id, quantity in requested_quantities.items()
            ],
        },
        reason=reason,
    )
    realtime_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.return_recorded",
        payload={
            "order_id": order.id,
            "order_number": order.order_number,
            "return_id": return_record.id,
            "kind": return_record.kind,
            "refund_amount": format(total_refund, ".3f"),
        },
    )
    inventory_event_ids.append(realtime_event.id)
    db.session.commit()
    _publish_inventory_events(inventory_event_ids)
    return order, return_record, False


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
            or_(OrderPayment.transaction_reference.is_(None), ~OrderPayment.transaction_reference.like("notice-deposit-credit:%")),
        )
        .group_by(OrderPayment.method)
    ).all()
    totals = {method: Decimal(str(amount or 0)).quantize(MONEY_QUANTUM) for method, amount in rows}
    # Commercial deposits are real cash/bank collections and belong in the same
    # daily closeout as POS receipts. They are held in the locked notice JSON
    # ledger for compatibility with imported legacy payments.
    notices = db.session.execute(
        select(DemandNotice).where(
            DemandNotice.tenant_container_id == company.tenant_container_id,
            DemandNotice.company_id == company.id,
            DemandNotice.store_id == store_id,
        )
    ).scalars()
    for notice in notices:
        for payment in notice.payments or []:
            if not isinstance(payment, dict) or payment.get("method") not in {"cash", "bank", "bank_transfer", "other"}:
                continue
            try:
                received_at = datetime.fromisoformat(str(payment.get("received_at", "")))
                if received_at.tzinfo is None:
                    received_at = received_at.replace(tzinfo=timezone.utc)
                received_at = received_at.astimezone(timezone.utc)
                amount = Decimal(str(payment.get("amount", "0"))).quantize(MONEY_QUANTUM)
            except (ValueError, InvalidOperation):
                continue
            if start <= received_at < end:
                method = payment["method"]
                totals[method] = totals.get(method, ZERO) + amount
    refund_rows = db.session.execute(
        select(OrderReturn.refund_method, func.coalesce(func.sum(OrderReturn.refund_amount), 0))
        .where(
            OrderReturn.tenant_container_id == company.tenant_container_id,
            OrderReturn.company_id == company.id,
            OrderReturn.store_id == store_id,
            OrderReturn.kind == "refund",
            OrderReturn.created_at >= start,
            OrderReturn.created_at < end,
        )
        .group_by(OrderReturn.refund_method)
    ).all()
    refunds = {method: Decimal(str(amount or 0)).quantize(MONEY_QUANTUM) for method, amount in refund_rows}
    return {
        method: totals.get(method, ZERO) - refunds.get(method, ZERO)
        for method in ("cash", "bank", "bank_transfer", "other")
    }


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
    realtime_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.cashup_changed",
        payload={"cashup_id": cashup.id, "business_date": business_date.isoformat(), "status": cashup.status},
    )
    db.session.commit()
    _publish_inventory_events([realtime_event.id])
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
    company = db.session.get(Company, cashup.company_id)
    store = _store_for_company(cashup.store_id, cashup.company_id)
    realtime_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.cashup_changed",
        payload={"cashup_id": cashup.id, "business_date": cashup.business_date.isoformat(), "status": cashup.status},
    )
    db.session.commit()
    _publish_inventory_events([realtime_event.id])
    return cashup


def list_sales_orders(actor: User, *, company_id: str | None = None, store_id: str | None = None, status: str | None = None, search: str | None = None, limit: int = 500) -> list[dict]:
    company = _company_for_actor(actor, company_id)
    allowed = accessible_store_ids(actor, company_id=company.id, tenant_container_id=company.tenant_container_id)
    allowed = {sid for sid in allowed if can_access_data_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="view", company_id=company.id, store_id=sid)}
    if store_id:
        store = _require_assigned_store(actor, store_id, company.id)
        _require_sales_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="view", company_id=company.id, store_id=store.id)
        allowed &= {store.id}
    if not allowed:
        return []
    statement = select(SalesOrder).where(
        SalesOrder.tenant_container_id == company.tenant_container_id,
        SalesOrder.company_id == company.id,
        SalesOrder.origin_store_id.in_(allowed),
    )
    if status and status != "all":
        if status not in {"open", "closed", "voided"}:
            raise SalesRuleError("Choose a valid order status.")
        statement = statement.where(SalesOrder.status == status)
    term = str(search or "").strip()[:80]
    if term:
        statement = statement.where(or_(
            SalesOrder.order_number.ilike(f"%{term}%"),
            SalesOrder.invoice_number.ilike(f"%{term}%"),
            SalesOrder.customer_name.ilike(f"%{term}%"),
            SalesOrder.customer_phone.ilike(f"%{term}%"),
        ))
    rows = db.session.execute(statement.order_by(SalesOrder.created_at.desc()).limit(max(1, min(int(limit), 1000)))).scalars()
    return [order_dict(order) for order in rows]


def update_order_fulfillment(actor: User, *, order_id: str, status: str, delivery_address: str | None = None, storekeeper_notes: str | None = None, company_id: str | None = None) -> SalesOrder:
    company = _company_for_actor(actor, company_id)
    order_ref = db.session.execute(select(SalesOrder).where(
        SalesOrder.id == order_id,
        SalesOrder.tenant_container_id == company.tenant_container_id,
        SalesOrder.company_id == company.id,
    )).scalar_one_or_none()
    if order_ref is None:
        raise SalesRuleError("Order not found.", 404, "not_found")
    order, store, company = _order_for_actor(actor, order_id, order_ref.origin_store_id, for_shared_bill=False, lock=True)
    sales_edit = can_access_data_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="edit", company_id=company.id, store_id=store.id)
    logistics_edit = actor.has_permission("manage_logistics") and can_access_data_domain(actor, tenant_container_id=company.tenant_container_id, domain="inventory", action="edit", company_id=company.id, store_id=store.id)
    if not (actor.is_admin or sales_edit or logistics_edit):
        raise SalesRuleError("You are not allowed to update delivery fulfillment.", 403, "permission_denied")
    if status not in {"pending", "partially_delivered", "delivered", "cancelled"}:
        raise SalesRuleError("Choose a valid delivery status.")
    transitions = {
        "pending": {"pending", "partially_delivered", "delivered", "cancelled"},
        "partially_delivered": {"partially_delivered", "delivered", "cancelled"},
        "delivered": {"delivered"},
        "cancelled": {"cancelled"},
    }
    if status not in transitions.get(order.delivery_status or "pending", {"pending"}):
        raise SalesRuleError("Delivery status cannot move backwards or reopen a terminal fulfillment.", 409, "invalid_transition")
    before = {"delivery_status": order.delivery_status, "delivery_address": order.delivery_address, "storekeeper_notes": order.storekeeper_notes}
    if delivery_address is not None:
        if not isinstance(delivery_address, str) or len(delivery_address.strip()) > 2000:
            raise SalesRuleError("Delivery address must be 2000 characters or fewer.")
        order.delivery_address = delivery_address.strip() or None
    if storekeeper_notes is not None:
        if not isinstance(storekeeper_notes, str) or len(storekeeper_notes.strip()) > 500:
            raise SalesRuleError("Storekeeper notes must be 500 characters or fewer.")
        order.storekeeper_notes = storekeeper_notes.strip() or None
    order.delivery_status = status
    order.updated_by_id = actor.id
    _add_audit(company.id, actor.id, "sales.fulfillment_updated", "sales_order", order.id, store_id=store.id, before=before,
               after={"delivery_status": status, "delivery_address": order.delivery_address, "storekeeper_notes": order.storekeeper_notes})
    realtime_event = _sales_realtime_event(
        company=company,
        store=store,
        actor=actor,
        event_type="sales.order_changed",
        payload={"order_id": order.id, "order_number": order.order_number, "status": order.status, "delivery_status": order.delivery_status},
    )
    db.session.commit()
    _publish_inventory_events([realtime_event.id])
    return order
