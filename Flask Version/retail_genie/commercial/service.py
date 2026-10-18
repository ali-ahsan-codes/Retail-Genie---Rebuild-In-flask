"""Commercial document rules and atomic conversion into open sales bills."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import or_, select

from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import (
    BusinessNumberSeries,
    CatalogProduct,
    Company,
    DemandNotice,
    Quotation,
    QuotationLine,
    SalesOrder,
    Store,
)
from ..sales.service import (
    MONEY_QUANTUM,
    SalesRuleError,
    _add_audit,
    _as_integer,
    _company_for_actor,
    _require_assigned_store,
    _require_sales_domain,
    as_money,
    company_today,
    create_order,
    normalize_phone,
    order_dict,
)


_PREFIXES = {"demand_notice": "DN-", "quotation": "QT-"}


def _document_number(company: Company, document_type: str) -> str:
    """Lock the company row before allocating/creating its per-type counter."""
    locked_company = db.session.execute(
        select(Company)
        .where(Company.id == company.id, Company.tenant_container_id == company.tenant_container_id)
        .with_for_update()
    ).scalar_one_or_none()
    if locked_company is None or not locked_company.is_active:
        raise SalesRuleError("Company not found.", 404, "not_found")
    series = db.session.execute(
        select(BusinessNumberSeries)
        .where(
            BusinessNumberSeries.tenant_container_id == company.tenant_container_id,
            BusinessNumberSeries.company_id == company.id,
            BusinessNumberSeries.document_type == document_type,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if series is None:
        series = BusinessNumberSeries(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            document_type=document_type,
            prefix=_PREFIXES[document_type],
            next_number=1,
        )
        db.session.add(series)
        db.session.flush()
    number = int(series.next_number)
    if number <= 0 or number > 999999999:
        raise SalesRuleError("Document number series is exhausted; contact an administrator.", 409, "series_exhausted")
    series.next_number = number + 1
    return f"{series.prefix}{number:06d}"


def _valid_date(value, *, field: str, required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise SalesRuleError(f"{field} is required.")
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise SalesRuleError(f"{field} must be a date.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise SalesRuleError(f"{field} must use YYYY-MM-DD format.") from None


def _optional_text(value, *, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SalesRuleError(f"{field} must be text.")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise SalesRuleError(f"{field} must be {maximum} characters or fewer.")
    return cleaned or None


def _parse_bool(value, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "yes", "on"):
        return True
    if value in (0, "0", "false", "False", "no", "off", None, ""):
        return False
    raise SalesRuleError(f"{field} must be true or false.")


def _authorized_company_store(actor, *, company_id: str | None, store_id: str, action: str):
    company = _company_for_actor(actor, company_id)
    store = _require_assigned_store(actor, store_id, company.id)
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="sales",
        action=action,
        company_id=company.id,
        store_id=store.id,
    )
    return company, store


def _product_for_document(actor, company: Company, store: Store, product_id: str) -> CatalogProduct:
    product = db.session.execute(
        select(CatalogProduct)
        .where(
            CatalogProduct.id == product_id,
            CatalogProduct.tenant_container_id == company.tenant_container_id,
            CatalogProduct.company_id == company.id,
            CatalogProduct.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if product is None:
        raise SalesRuleError("Catalog product not found.", 404, "not_found")
    _require_sales_domain(
        actor,
        tenant_container_id=company.tenant_container_id,
        domain="product_catalog",
        action="view",
        company_id=company.id,
        store_id=store.id,
    )
    return product


def demand_notice_dict(notice: DemandNotice) -> dict:
    linked_order = db.session.execute(
        select(SalesOrder).where(
            SalesOrder.tenant_container_id == notice.tenant_container_id,
            SalesOrder.company_id == notice.company_id,
            SalesOrder.source_demand_notice_id == notice.id,
        )
    ).scalar_one_or_none()
    return {
        "id": notice.id,
        "tenant_container_id": notice.tenant_container_id,
        "company_id": notice.company_id,
        "store_id": notice.store_id,
        "notice_number": notice.notice_number,
        "salesperson_id": notice.salesperson_id,
        "customer_name": notice.customer_name,
        "customer_phone": notice.customer_phone,
        "product_id": notice.product_id,
        "product_name": notice.product_name,
        "product_sku": notice.product_sku,
        "quantity_requested": notice.quantity_requested,
        "quantity_fulfilled": notice.quantity_fulfilled,
        "agreed_price": format(Decimal(notice.agreed_price), ".3f") if notice.agreed_price is not None else None,
        "expected_availability_date": notice.expected_availability_date.isoformat() if notice.expected_availability_date else None,
        "status": notice.status,
        "is_new_product": bool(notice.is_new_product),
        "notes": notice.notes,
        "linked_order_id": linked_order.id if linked_order else None,
        "linked_order_number": linked_order.order_number if linked_order else None,
        "created_at": notice.created_at.isoformat() if notice.created_at else None,
        "updated_at": notice.updated_at.isoformat() if notice.updated_at else None,
    }


def quotation_dict(quotation: Quotation) -> dict:
    lines = db.session.execute(
        select(QuotationLine)
        .where(
            QuotationLine.tenant_container_id == quotation.tenant_container_id,
            QuotationLine.company_id == quotation.company_id,
            QuotationLine.quotation_id == quotation.id,
        )
        .order_by(QuotationLine.line_number.asc())
    ).scalars().all()
    linked_order = db.session.execute(
        select(SalesOrder).where(
            SalesOrder.tenant_container_id == quotation.tenant_container_id,
            SalesOrder.company_id == quotation.company_id,
            SalesOrder.source_quotation_id == quotation.id,
        )
    ).scalar_one_or_none()
    return {
        "id": quotation.id,
        "tenant_container_id": quotation.tenant_container_id,
        "company_id": quotation.company_id,
        "store_id": quotation.store_id,
        "quotation_number": quotation.quotation_number,
        "salesperson_id": quotation.salesperson_id,
        "customer_name": quotation.customer_name,
        "customer_phone": quotation.customer_phone,
        "customer_email": quotation.customer_email,
        "customer_address": quotation.customer_address,
        "preparation_days": quotation.preparation_days,
        "valid_until": quotation.valid_until.isoformat() if quotation.valid_until else None,
        "status": quotation.status,
        "total_amount": format(Decimal(quotation.total_amount), ".3f"),
        "notes": quotation.notes,
        "linked_order_id": linked_order.id if linked_order else None,
        "linked_order_number": linked_order.order_number if linked_order else None,
        "lines": [
            {
                "id": line.id,
                "product_id": line.product_id,
                "product_name": line.product_name,
                "product_sku": line.product_sku,
                "unit_price": format(Decimal(line.unit_price), ".3f"),
                "quantity": line.quantity,
                "line_total": format(Decimal(line.line_total), ".3f"),
                "is_external": bool(line.is_external),
                "converted": bool(line.converted),
            }
            for line in lines
        ],
        "created_at": quotation.created_at.isoformat() if quotation.created_at else None,
        "updated_at": quotation.updated_at.isoformat() if quotation.updated_at else None,
    }


def create_demand_notice(
    actor,
    *,
    store_id: str,
    customer_phone: str,
    product_name: str | None = None,
    product_id: str | None = None,
    product_sku: str | None = None,
    quantity_requested,
    customer_name: str | None = None,
    agreed_price=None,
    expected_availability_date=None,
    is_new_product=None,
    notes: str | None = None,
    company_id: str | None = None,
) -> DemandNotice:
    company, store = _authorized_company_store(actor, company_id=company_id, store_id=store_id, action="add")
    phone_search = normalize_phone(customer_phone)
    phone = customer_phone.strip()
    if len(phone) > 64:
        raise SalesRuleError("Customer phone number is too long.")
    name = _optional_text(customer_name, field="Customer name", maximum=160)
    quantity = _as_integer(quantity_requested, field="Requested quantity")
    product = _product_for_document(actor, company, store, product_id) if product_id else None
    resolved_name = product.name if product is not None else _optional_text(product_name, field="Product name", maximum=255)
    if not resolved_name:
        raise SalesRuleError("Choose a catalog product or enter the requested product name.")
    sku = product.sku if product is not None else _optional_text(product_sku, field="Product SKU", maximum=128)
    price = as_money(agreed_price, field="Agreed price", allow_zero=False) if agreed_price not in (None, "") else None
    expected_date = _valid_date(expected_availability_date, field="Expected availability date")
    new_product = (product is None) if is_new_product is None else _parse_bool(is_new_product, field="New product flag")
    if product is not None and new_product:
        raise SalesRuleError("A catalog product cannot be marked as a new product.")
    note = _optional_text(notes, field="Notes", maximum=2000)
    number = _document_number(company, "demand_notice")
    notice = DemandNotice(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        store_id=store.id,
        notice_number=number,
        salesperson_id=actor.id,
        customer_name=name,
        customer_phone=phone,
        phone_search=phone_search,
        product_owner_company_id=product.company_id if product else None,
        product_id=product.id if product else None,
        product_name=resolved_name,
        product_sku=sku,
        quantity_requested=quantity,
        quantity_fulfilled=0,
        agreed_price=price,
        expected_availability_date=expected_date,
        status="open",
        is_new_product=new_product,
        notes=note,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(notice)
    db.session.flush()
    _add_audit(
        company.id,
        actor.id,
        "demand_notice.created",
        "demand_notice",
        notice.id,
        store_id=store.id,
        after={
            "notice_number": number,
            "product_id": notice.product_id,
            "quantity_requested": quantity,
            "customer_phone": phone_search,
            "status": notice.status,
        },
    )
    db.session.commit()
    return notice


def list_demand_notices(actor, *, company_id: str | None = None, store_id: str | None = None, status: str | None = None, search: str | None = None) -> list[dict]:
    company = _company_for_actor(actor, company_id)
    allowed_store_ids = accessible_store_ids(actor, company_id=company.id, tenant_container_id=company.tenant_container_id)
    allowed_store_ids = {
        candidate_id
        for candidate_id in allowed_store_ids
        if can_access_data_domain(
            actor,
            tenant_container_id=company.tenant_container_id,
            domain="sales",
            action="view",
            company_id=company.id,
            store_id=candidate_id,
        )
    }
    if store_id:
        store = _require_assigned_store(actor, store_id, company.id)
        _require_sales_domain(
            actor,
            tenant_container_id=company.tenant_container_id,
            domain="sales",
            action="view",
            company_id=company.id,
            store_id=store.id,
        )
        allowed_store_ids &= {store.id}
    if not allowed_store_ids:
        return []
    query = select(DemandNotice).where(
        DemandNotice.tenant_container_id == company.tenant_container_id,
        DemandNotice.company_id == company.id,
        DemandNotice.store_id.in_(allowed_store_ids),
    )
    if status:
        if status not in {"open", "converted", "cancelled"}:
            raise SalesRuleError("Unknown demand notice status.")
        query = query.where(DemandNotice.status == status)
    value = str(search or "").strip()[:80]
    if value:
        criteria = [
            DemandNotice.notice_number.ilike(f"%{value}%"),
            DemandNotice.product_name.ilike(f"%{value}%"),
            DemandNotice.customer_name.ilike(f"%{value}%"),
        ]
        try:
            criteria.append(DemandNotice.phone_search == normalize_phone(value))
        except SalesRuleError:
            pass
        query = query.where(or_(*criteria))
    rows = db.session.execute(query.order_by(DemandNotice.created_at.desc()).limit(200)).scalars().all()
    return [demand_notice_dict(row) for row in rows]


def cancel_demand_notice(actor, *, notice_id: str, reason: str, company_id: str | None = None) -> DemandNotice:
    company = _company_for_actor(actor, company_id)
    statement = select(DemandNotice).where(
        DemandNotice.id == notice_id,
        DemandNotice.tenant_container_id == company.tenant_container_id,
        DemandNotice.company_id == company.id,
    ).with_for_update()
    notice = db.session.execute(statement).scalar_one_or_none()
    if notice is None:
        raise SalesRuleError("Demand notice not found.", 404, "not_found")
    store = _require_assigned_store(actor, notice.store_id, company.id)
    _require_sales_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="edit", company_id=company.id, store_id=store.id)
    if notice.status != "open":
        raise SalesRuleError("Only an open demand notice can be cancelled.", 409, "invalid_state")
    note = _optional_text(reason, field="Cancellation reason", maximum=500)
    if not note:
        raise SalesRuleError("A cancellation reason is required.")
    notice.status = "cancelled"
    notice.updated_by_id = actor.id
    _add_audit(
        company.id,
        actor.id,
        "demand_notice.cancelled",
        "demand_notice",
        notice.id,
        store_id=store.id,
        before={"status": "open"},
        after={"status": "cancelled"},
        reason=note,
    )
    db.session.commit()
    return notice


def create_quotation(
    actor,
    *,
    store_id: str,
    customer_phone: str,
    lines: list[dict],
    customer_name: str | None = None,
    customer_email: str | None = None,
    customer_address: str | None = None,
    preparation_days=0,
    valid_until=None,
    notes: str | None = None,
    company_id: str | None = None,
) -> Quotation:
    company, store = _authorized_company_store(actor, company_id=company_id, store_id=store_id, action="add")
    if not isinstance(lines, list) or not lines or len(lines) > 50:
        raise SalesRuleError("Add between one and 50 quotation lines.")
    phone = customer_phone.strip() if isinstance(customer_phone, str) else ""
    normalize_phone(phone)
    if len(phone) > 64:
        raise SalesRuleError("Customer phone number is too long.")
    name = _optional_text(customer_name, field="Customer name", maximum=160)
    email = _optional_text(customer_email, field="Customer email", maximum=254)
    address = _optional_text(customer_address, field="Customer address", maximum=2000)
    prep = _as_integer(preparation_days, field="Preparation days", minimum=0)
    expiry = _valid_date(valid_until, field="Valid until")
    note = _optional_text(notes, field="Notes", maximum=4000)
    now_date = company_today(company)
    if expiry is not None and expiry < now_date:
        raise SalesRuleError("Quotation validity date cannot be in the past.")

    normalized_lines = []
    total = Decimal("0.000")
    for index, raw in enumerate(lines, start=1):
        if not isinstance(raw, dict):
            raise SalesRuleError(f"Quotation line {index} must be an object.")
        external = _parse_bool(raw.get("is_external", False), field=f"Line {index} external flag")
        product_id = str(raw.get("product_id") or "").strip()
        product = None
        if external:
            if product_id:
                raise SalesRuleError(f"External quotation line {index} cannot reference a catalog product.")
            product_name = _optional_text(raw.get("product_name"), field=f"Line {index} product name", maximum=255)
            product_sku = _optional_text(raw.get("product_sku"), field=f"Line {index} product SKU", maximum=128)
            if not product_name:
                raise SalesRuleError(f"Line {index} product name is required.")
        else:
            if not product_id:
                raise SalesRuleError(f"Select an active catalog product on quotation line {index}.")
            product = _product_for_document(actor, company, store, product_id)
            product_name = product.name
            product_sku = product.sku
        quantity = _as_integer(raw.get("quantity"), field=f"Line {index} quantity")
        price_raw = raw.get("unit_price")
        if price_raw in (None, "") and product is not None:
            price_raw = product.price
        price = as_money(price_raw, field=f"Line {index} unit price", allow_zero=False)
        line_total = (price * quantity).quantize(MONEY_QUANTUM)
        total += line_total
        if total >= Decimal("100000000000"):
            raise SalesRuleError("Quotation total exceeds the supported amount.")
        normalized_lines.append(
            {
                "product": product,
                "product_name": product_name,
                "product_sku": product_sku,
                "quantity": quantity,
                "unit_price": price,
                "line_total": line_total,
                "is_external": external,
            }
        )

    number = _document_number(company, "quotation")
    quotation = Quotation(
        tenant_container_id=company.tenant_container_id,
        company_id=company.id,
        store_id=store.id,
        quotation_number=number,
        salesperson_id=actor.id,
        customer_name=name,
        customer_phone=phone,
        customer_email=email,
        customer_address=address,
        preparation_days=prep,
        valid_until=expiry,
        status="draft",
        total_amount=total,
        notes=note,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(quotation)
    db.session.flush()
    for line_number, item in enumerate(normalized_lines, start=1):
        product = item["product"]
        db.session.add(
            QuotationLine(
                tenant_container_id=company.tenant_container_id,
                company_id=company.id,
                quotation_id=quotation.id,
                line_number=line_number,
                product_owner_company_id=product.company_id if product else None,
                product_id=product.id if product else None,
                product_name=item["product_name"],
                product_sku=item["product_sku"],
                unit_price=item["unit_price"],
                quantity=item["quantity"],
                line_total=item["line_total"],
                is_external=item["is_external"],
                converted=False,
            )
        )
    db.session.flush()
    _add_audit(
        company.id,
        actor.id,
        "quotation.created",
        "quotation",
        quotation.id,
        store_id=store.id,
        after={"quotation_number": number, "line_count": len(normalized_lines), "total_amount": format(total, ".3f"), "status": "draft"},
    )
    db.session.commit()
    return quotation


def _quotation_for_actor(actor, quotation_id: str, *, company_id: str | None = None, lock: bool = False):
    company = _company_for_actor(actor, company_id)
    statement = select(Quotation).where(
        Quotation.id == quotation_id,
        Quotation.tenant_container_id == company.tenant_container_id,
        Quotation.company_id == company.id,
    )
    if lock:
        statement = statement.with_for_update()
    quotation = db.session.execute(statement).scalar_one_or_none()
    if quotation is None:
        raise SalesRuleError("Quotation not found.", 404, "not_found")
    store = _require_assigned_store(actor, quotation.store_id, company.id)
    return company, store, quotation


def list_quotations(actor, *, company_id: str | None = None, store_id: str | None = None, status: str | None = None, search: str | None = None) -> list[dict]:
    company = _company_for_actor(actor, company_id)
    allowed_store_ids = accessible_store_ids(actor, company_id=company.id, tenant_container_id=company.tenant_container_id)
    allowed_store_ids = {
        candidate_id
        for candidate_id in allowed_store_ids
        if can_access_data_domain(
            actor,
            tenant_container_id=company.tenant_container_id,
            domain="sales",
            action="view",
            company_id=company.id,
            store_id=candidate_id,
        )
    }
    if store_id:
        store = _require_assigned_store(actor, store_id, company.id)
        _require_sales_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="view", company_id=company.id, store_id=store.id)
        allowed_store_ids &= {store.id}
    if not allowed_store_ids:
        return []
    query = select(Quotation).where(
        Quotation.tenant_container_id == company.tenant_container_id,
        Quotation.company_id == company.id,
        Quotation.store_id.in_(allowed_store_ids),
    )
    if status:
        if status not in {"draft", "sent", "accepted", "rejected", "cancelled", "expired", "converted"}:
            raise SalesRuleError("Unknown quotation status.")
        query = query.where(Quotation.status == status)
    value = str(search or "").strip()[:80]
    if value:
        query = query.where(
            or_(
                Quotation.quotation_number.ilike(f"%{value}%"),
                Quotation.customer_name.ilike(f"%{value}%"),
                Quotation.customer_phone.ilike(f"%{value}%"),
            )
        )
    rows = db.session.execute(query.order_by(Quotation.created_at.desc()).limit(200)).scalars().all()
    return [quotation_dict(row) for row in rows]


def change_quotation_status(actor, *, quotation_id: str, status: str, company_id: str | None = None) -> Quotation:
    if status not in {"sent", "accepted", "rejected", "cancelled"}:
        raise SalesRuleError("Quotation status must be sent, accepted, rejected, or cancelled.")
    company, store, quotation = _quotation_for_actor(actor, quotation_id, company_id=company_id, lock=True)
    _require_sales_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="edit", company_id=company.id, store_id=store.id)
    allowed_transitions = {
        "draft": {"sent", "cancelled"},
        "sent": {"accepted", "rejected", "cancelled"},
        "accepted": {"rejected", "cancelled"},
    }
    if status not in allowed_transitions.get(quotation.status, set()):
        raise SalesRuleError(f"A quotation cannot move from {quotation.status} to {status}.", 409, "invalid_state")
    if status == "accepted" and quotation.valid_until is not None and quotation.valid_until < company_today(company):
        quotation.status = "expired"
        quotation.updated_by_id = actor.id
        _add_audit(company.id, actor.id, "quotation.expired", "quotation", quotation.id, store_id=store.id, before={"status": "sent"}, after={"status": "expired"}, reason="validity date passed")
        db.session.commit()
        raise SalesRuleError("This quotation has expired.", 409, "quotation_expired")
    before = quotation.status
    quotation.status = status
    quotation.updated_by_id = actor.id
    _add_audit(company.id, actor.id, f"quotation.{status}", "quotation", quotation.id, store_id=store.id, before={"status": before}, after={"status": status})
    db.session.commit()
    return quotation


def convert_quotation_to_order(actor, *, quotation_id: str, company_id: str | None = None) -> tuple[SalesOrder, bool]:
    company, store, quotation = _quotation_for_actor(actor, quotation_id, company_id=company_id, lock=True)
    _require_sales_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="add", company_id=company.id, store_id=store.id)
    prior = db.session.execute(
        select(SalesOrder).where(
            SalesOrder.tenant_container_id == company.tenant_container_id,
            SalesOrder.company_id == company.id,
            SalesOrder.source_quotation_id == quotation.id,
        )
    ).scalar_one_or_none()
    if prior is not None:
        return prior, True
    if quotation.status != "accepted":
        raise SalesRuleError("Only an accepted quotation can be converted to an open bill.", 409, "invalid_state")
    if quotation.valid_until is not None and quotation.valid_until < company_today(company):
        quotation.status = "expired"
        quotation.updated_by_id = actor.id
        _add_audit(company.id, actor.id, "quotation.expired", "quotation", quotation.id, store_id=store.id, before={"status": "accepted"}, after={"status": "expired"}, reason="validity date passed")
        db.session.commit()
        raise SalesRuleError("This quotation has expired.", 409, "quotation_expired")
    lines = db.session.execute(
        select(QuotationLine).where(
            QuotationLine.tenant_container_id == company.tenant_container_id,
            QuotationLine.company_id == company.id,
            QuotationLine.quotation_id == quotation.id,
        ).order_by(QuotationLine.line_number.asc())
    ).scalars().all()
    if not lines or any(line.is_external or not line.product_id for line in lines):
        raise SalesRuleError("Convert external quotation lines to catalog products before creating a stock-backed bill.", 409, "external_line_unlinked")
    items = [{"product_id": line.product_id, "quantity": line.quantity} for line in lines]
    prices = [line.unit_price for line in lines]
    order = create_order(
        actor,
        store_id=quotation.store_id,
        customer_phone=quotation.customer_phone,
        customer_name=quotation.customer_name,
        items=items,
        company_id=company.id,
        source_quotation_id=quotation.id,
        line_price_overrides=prices,
    )
    return order, False


def convert_demand_notice_to_order(actor, *, notice_id: str, company_id: str | None = None) -> tuple[SalesOrder, bool]:
    company = _company_for_actor(actor, company_id)
    notice = db.session.execute(
        select(DemandNotice).where(
            DemandNotice.id == notice_id,
            DemandNotice.tenant_container_id == company.tenant_container_id,
            DemandNotice.company_id == company.id,
        ).with_for_update()
    ).scalar_one_or_none()
    if notice is None:
        raise SalesRuleError("Demand notice not found.", 404, "not_found")
    store = _require_assigned_store(actor, notice.store_id, company.id)
    _require_sales_domain(actor, tenant_container_id=company.tenant_container_id, domain="sales", action="add", company_id=company.id, store_id=store.id)
    prior = db.session.execute(
        select(SalesOrder).where(
            SalesOrder.tenant_container_id == company.tenant_container_id,
            SalesOrder.company_id == company.id,
            SalesOrder.source_demand_notice_id == notice.id,
        )
    ).scalar_one_or_none()
    if prior is not None:
        return prior, True
    if notice.status != "open":
        raise SalesRuleError("Only an open demand notice can be converted.", 409, "invalid_state")
    if not notice.product_id:
        raise SalesRuleError("Link this demand notice to a catalog product before conversion.", 409, "product_link_required")
    overrides = [notice.agreed_price] if notice.agreed_price is not None else None
    order = create_order(
        actor,
        store_id=notice.store_id,
        customer_phone=notice.customer_phone,
        customer_name=notice.customer_name,
        items=[{"product_id": notice.product_id, "quantity": notice.quantity_requested}],
        company_id=company.id,
        source_demand_notice_id=notice.id,
        line_price_overrides=overrides,
    )
    return order, False
