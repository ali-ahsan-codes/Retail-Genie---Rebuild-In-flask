"""Tenant- and store-scoped sales, activity, and salesperson reporting."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership, current_tenant_container_id
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import AuditEvent, Company, DemandNotice, OrderPayment, SalesOrder, Store, TenantContainer, User


class ReportRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _scope(actor: User, company_id: str | None = None, store_id: str | None = None):
    tenant_id = current_tenant_container_id(actor)
    if not tenant_id:
        raise ReportRuleError("Select an active tenant container first.", 403, "tenant_forbidden")
    container = db.session.get(TenantContainer, tenant_id)
    if container is None or not container.is_active:
        raise ReportRuleError("Tenant container not found.", 404, "not_found")
    if actor.is_super_admin:
        if not company_id:
            raise ReportRuleError("Select a company.", 400, "company_required")
        company = db.session.get(Company, company_id)
    else:
        membership = current_membership(actor, tenant_container_id=tenant_id)
        company = db.session.get(Company, membership.company_id) if membership and membership.company_id else None
        if company_id and company and company_id != company.id:
            company = None
    if company is None or company.tenant_container_id != tenant_id or not company.is_active:
        raise ReportRuleError("Company not found.", 404, "not_found")
    if not actor.is_super_admin and not actor.is_company_admin:
        allowed = can_access_data_domain(
            actor,
            tenant_container_id=tenant_id,
            domain="reports",
            action="view",
            company_id=company.id,
            store_id=store_id,
        ) or actor.has_permission("view_reports") or actor.has_permission("view_salesperson_reports")
        if not allowed:
            raise ReportRuleError("Report permission is required.", 403, "permission_denied")
    accessible = accessible_store_ids(actor, company_id=company.id, tenant_container_id=tenant_id)
    if store_id:
        store = db.session.execute(
            select(Store).where(
                Store.id == store_id,
                Store.tenant_container_id == tenant_id,
                Store.company_id == company.id,
                Store.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if store is None or store.id not in accessible:
            raise ReportRuleError("You do not have access to this store.", 403, "store_forbidden")
        if not can_access_data_domain(
            actor,
            tenant_container_id=tenant_id,
            domain="reports",
            action="view",
            company_id=company.id,
            store_id=store.id,
        ) and not (actor.is_super_admin or actor.is_company_admin or actor.has_permission("view_reports")):
            raise ReportRuleError("Report permission is required.", 403, "permission_denied")
        accessible = {store.id}
    return tenant_id, company, accessible


def sales_report(
    actor: User,
    *,
    company_id: str | None = None,
    store_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    salesperson_id: str | None = None,
) -> dict:
    tenant_id, company, store_ids = _scope(actor, company_id, store_id)
    if start_date and end_date and end_date < start_date:
        raise ReportRuleError("End date cannot be before start date.")
    try:
        today = datetime.now(ZoneInfo(company.timezone)).date()
    except (ZoneInfoNotFoundError, ValueError):
        raise ReportRuleError("The company timezone is not configured correctly.", 500, "invalid_company_timezone") from None
    end_date = end_date or today
    start_date = start_date or (end_date - timedelta(days=29))
    if (end_date - start_date).days > 366:
        raise ReportRuleError("A report may cover at most 367 days.")
    if not store_ids:
        return {"company_id": company.id, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "orders": [], "totals": {}}
    statement = select(SalesOrder).where(
        SalesOrder.tenant_container_id == tenant_id,
        SalesOrder.company_id == company.id,
        SalesOrder.origin_store_id.in_(store_ids),
        SalesOrder.business_date >= start_date,
        SalesOrder.business_date <= end_date,
    )
    may_view_company_sales = actor.is_admin or actor.has_permission("view_reports")
    if salesperson_id is None and actor.has_permission("view_salesperson_reports") and not may_view_company_sales:
        salesperson_id = actor.id
    if salesperson_id:
        if salesperson_id != actor.id and not may_view_company_sales:
            raise ReportRuleError("You may only view your own salesperson report.", 403, "permission_denied")
        statement = statement.where(
            (SalesOrder.primary_salesperson_id == salesperson_id)
            | (SalesOrder.secondary_salesperson_id == salesperson_id)
            | (SalesOrder.created_by_id == salesperson_id)
        )
    orders = list(db.session.execute(statement.order_by(SalesOrder.business_date.desc(), SalesOrder.created_at.desc()).limit(5000)).scalars())
    order_rows = []
    order_ids = [row.id for row in orders]
    payment_totals: dict[str, Decimal] = {}
    direct_payment_totals: dict[str, Decimal] = {}
    deposit_credit_by_order: dict[str, Decimal] = {}
    by_tender: dict[str, Decimal] = {}
    deposit_credit_applied = Decimal("0")
    for payment in db.session.execute(
        select(OrderPayment).where(
            OrderPayment.tenant_container_id == tenant_id,
            OrderPayment.company_id == company.id,
            OrderPayment.order_id.in_(order_ids) if order_ids else False,
        )
    ).scalars():
        amount = Decimal(str(payment.amount))
        payment_totals[payment.order_id] = payment_totals.get(payment.order_id, Decimal("0")) + amount
        if (payment.transaction_reference or "").startswith("notice-deposit-credit:"):
            deposit_credit_applied += amount
            deposit_credit_by_order[payment.order_id] = deposit_credit_by_order.get(payment.order_id, Decimal("0")) + amount
        else:
            direct_payment_totals[payment.order_id] = direct_payment_totals.get(payment.order_id, Decimal("0")) + amount
            by_tender[payment.method] = by_tender.get(payment.method, Decimal("0")) + amount
    gross = Decimal("0")
    paid = Decimal("0")
    settled_paid = Decimal("0")
    for order in orders:
        order_paid = payment_totals.get(order.id, Decimal("0"))
        gross += Decimal(str(order.total_amount or 0))
        settled_paid += order_paid
        paid += direct_payment_totals.get(order.id, Decimal("0"))
        order_rows.append(
            {
                "id": order.id,
                "order_number": order.order_number,
                "invoice_number": order.invoice_number,
                "business_date": order.business_date.isoformat(),
                "store_id": order.origin_store_id,
                "customer_name": order.customer_name,
                "customer_phone": order.customer_phone,
                "status": order.status,
                "subtotal": str(order.subtotal_amount or order.total_amount),
                "discount": str(order.discount_amount or 0),
                "total": str(order.total_amount),
                "paid": str(order_paid),
                "direct_paid": str(direct_payment_totals.get(order.id, Decimal("0"))),
                "deposit_credit_applied": str(deposit_credit_by_order.get(order.id, Decimal("0"))),
                "primary_salesperson_id": order.primary_salesperson_id,
                "secondary_salesperson_id": order.secondary_salesperson_id,
            }
        )
    deposit_rows = []
    deposit_totals: dict[str, Decimal] = {}
    deposit_gross = Decimal("0")
    notices = db.session.execute(select(DemandNotice).where(
        DemandNotice.tenant_container_id == tenant_id,
        DemandNotice.company_id == company.id,
        DemandNotice.store_id.in_(store_ids),
    )).scalars()
    zone = ZoneInfo(company.timezone)
    for notice in notices:
        for payment in notice.payments or []:
            if not isinstance(payment, dict) or payment.get("method") not in {"cash", "bank", "bank_transfer", "other"}:
                continue
            try:
                received = datetime.fromisoformat(str(payment.get("received_at", "")))
                if received.tzinfo is None:
                    received = received.replace(tzinfo=timezone.utc)
                local_date = received.astimezone(zone).date()
                amount = Decimal(str(payment.get("amount", "0")))
            except (ValueError, TypeError, ArithmeticError):
                continue
            if not start_date <= local_date <= end_date or amount <= 0:
                continue
            method = payment["method"]
            deposit_gross += amount
            deposit_totals[method] = deposit_totals.get(method, Decimal("0")) + amount
            deposit_rows.append({
                "notice_number": notice.notice_number,
                "business_date": local_date.isoformat(),
                "store_id": notice.store_id,
                "customer_name": notice.customer_name,
                "amount": format(amount, ".3f"),
                "method": method,
                "received_at": received.isoformat(),
            })
    deposit_rows.sort(key=lambda row: row["received_at"], reverse=True)
    return {
        "company_id": company.id,
        "company_name": company.name,
        "deposits": deposit_rows,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "orders": order_rows,
        "totals": {
            "order_count": len(orders),
            "gross_omr": format(gross, ".3f"),
            "paid_omr": format(paid, ".3f"),
            "order_paid_omr": format(settled_paid, ".3f"),
            "deposit_credit_applied_omr": format(deposit_credit_applied, ".3f"),
            "cash_collected_omr": format(paid + deposit_gross, ".3f"),
            "outstanding_omr": format(gross - settled_paid, ".3f"),
            "by_tender": {key: format(value, ".3f") for key, value in sorted(by_tender.items())},
            "commercial_deposits_omr": format(deposit_gross, ".3f"),
            "commercial_deposits_by_tender": {key: format(value, ".3f") for key, value in sorted(deposit_totals.items())},
        },
    }


def activity_log(actor: User, *, company_id: str | None = None, store_id: str | None = None, limit: int = 200) -> list[dict]:
    tenant_id, company, store_ids = _scope(actor, company_id, store_id)
    if not (actor.is_admin or actor.has_permission("view_activity_logs") or actor.has_permission("audit.view")):
        raise ReportRuleError("Activity log permission is required.", 403, "permission_denied")
    statement = select(AuditEvent).where(
        AuditEvent.tenant_container_id == tenant_id,
        AuditEvent.company_id == company.id,
    )
    if store_id:
        statement = statement.where(AuditEvent.store_id == store_id)
    elif store_ids and not (actor.is_admin or actor.is_super_admin):
        statement = statement.where((AuditEvent.store_id.is_(None)) | (AuditEvent.store_id.in_(store_ids)))
    rows = db.session.execute(statement.order_by(AuditEvent.created_at.desc()).limit(min(max(limit, 1), 500))).scalars()
    return [
        {
            "id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "store_id": row.store_id,
            "actor_user_id": row.actor_user_id,
            "reason": row.reason,
            "before": row.before_data,
            "after": row.after_data,
            "created_at": row.created_at.isoformat().replace("+00:00", "Z") if row.created_at else None,
        }
        for row in rows
    ]


def report_csv(report: dict) -> str:
    def safe_cell(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value

    stream = io.StringIO()
    writer = csv.DictWriter(
        stream,
        fieldnames=("record_type", "business_date", "order_number", "invoice_number", "notice_number", "method", "store_id", "customer_name", "status", "subtotal", "discount", "total", "paid", "direct_paid", "deposit_credit_applied"),
    )
    writer.writeheader()
    for row in report["orders"]:
        writer.writerow({key: safe_cell({**row, "record_type": "sale"}.get(key, "")) for key in writer.fieldnames})
    for row in report.get("deposits", []):
        writer.writerow({
            "record_type": "commercial_deposit",
            "business_date": safe_cell(row.get("business_date", "")),
            "notice_number": safe_cell(row.get("notice_number", "")),
            "method": safe_cell(row.get("method", "")),
            "store_id": safe_cell(row.get("store_id", "")),
            "customer_name": safe_cell(row.get("customer_name", "")),
            "status": "received",
            "paid": safe_cell(row.get("amount", "")),
        })
    return stream.getvalue()
