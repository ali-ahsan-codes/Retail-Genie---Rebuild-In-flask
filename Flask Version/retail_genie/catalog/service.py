"""Business rules for tenant-scoped products and store inventory."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy import func, or_, select

from ..auth.store_scope import accessible_store_ids, can_access_store
from ..auth.tenant_context import current_tenant_container_id
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import (
    AuditEvent,
    CatalogProduct,
    Company,
    InventoryBalance,
    InventoryMovement,
    RealtimeEvent,
    Store,
    TenantContainer,
    User,
)


class CatalogRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _tenant_for_actor(actor: User, tenant_container_id: str | None = None) -> str:
    active_id = current_tenant_container_id(actor)
    requested_id = tenant_container_id or active_id
    if not requested_id or requested_id != active_id:
        raise CatalogRuleError("Select an active tenant container first.", 403, "tenant_forbidden")
    container = db.session.get(TenantContainer, requested_id)
    if container is None or not container.is_active:
        raise CatalogRuleError("Tenant container not found.", 404, "not_found")
    return requested_id


def _company_in_tenant(company_id: str, tenant_container_id: str) -> Company:
    company = db.session.execute(
        select(Company).where(
            Company.id == company_id,
            Company.tenant_container_id == tenant_container_id,
            Company.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if company is None:
        raise CatalogRuleError("Company not found.", 404, "not_found")
    return company


def _store_in_tenant(store_id: str, tenant_container_id: str, *, lock: bool = False) -> Store:
    statement = select(Store).where(
        Store.id == store_id,
        Store.tenant_container_id == tenant_container_id,
        Store.is_active.is_(True),
    )
    if lock:
        statement = statement.with_for_update()
    store = db.session.execute(statement).scalar_one_or_none()
    if store is None:
        raise CatalogRuleError("Store not found.", 404, "not_found")
    _company_in_tenant(store.company_id, tenant_container_id)
    return store


def _product_in_tenant(product_id: str, tenant_container_id: str, *, lock: bool = False) -> CatalogProduct:
    statement = select(CatalogProduct).where(
        CatalogProduct.id == product_id,
        CatalogProduct.tenant_container_id == tenant_container_id,
    )
    if lock:
        statement = statement.with_for_update()
    product = db.session.execute(statement).scalar_one_or_none()
    if product is None:
        raise CatalogRuleError("Product not found.", 404, "not_found")
    return product


def _catalog_store_for_actor(
    actor: User,
    *,
    tenant_container_id: str,
    company_id: str,
    requested_store_id: str | None = None,
) -> Store:
    allowed_ids = accessible_store_ids(
        actor,
        company_id=company_id,
        tenant_container_id=tenant_container_id,
    )
    if not allowed_ids:
        raise CatalogRuleError("A store assignment is required to manage this company's catalog.", 403, "store_forbidden")
    if requested_store_id not in (None, ""):
        if not isinstance(requested_store_id, str) or requested_store_id not in allowed_ids:
            raise CatalogRuleError("You do not have access to this store.", 403, "store_forbidden")
        return _store_in_tenant(requested_store_id, tenant_container_id)
    return db.session.execute(
        select(Store)
        .where(
            Store.tenant_container_id == tenant_container_id,
            Store.company_id == company_id,
            Store.id.in_(allowed_ids),
            Store.is_active.is_(True),
        )
        .order_by(Store.code.asc())
        .limit(1)
    ).scalar_one()


def _require_domain(
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
        raise CatalogRuleError(f"You are not allowed to {action} this {domain.replace('_', ' ')} data.", 403, "permission_denied")


def accessible_stores(actor: User, *, tenant_container_id: str | None = None) -> list[Store]:
    tenant_id = _tenant_for_actor(actor, tenant_container_id)
    ids = accessible_store_ids(actor, tenant_container_id=tenant_id)
    if not ids:
        return []
    return list(
        db.session.execute(
            select(Store)
            .where(
                Store.tenant_container_id == tenant_id,
                Store.id.in_(ids),
                Store.is_active.is_(True),
            )
            .order_by(Store.company_id.asc(), Store.code.asc())
        ).scalars()
    )


def list_products(
    actor: User,
    *,
    store_id: str,
    search: str | None = None,
    tenant_container_id: str | None = None,
    limit: int | None = 500,
) -> tuple[list[dict], Store, bool]:
    tenant_id = _tenant_for_actor(actor, tenant_container_id)
    store = _store_in_tenant(store_id, tenant_id)
    if not can_access_store(
        actor,
        store.id,
        company_id=store.company_id,
        tenant_container_id=tenant_id,
    ):
        raise CatalogRuleError("You do not have access to this store.", 403, "store_forbidden")

    company_ids = [
        company.id
        for company in db.session.execute(
            select(Company).where(
                Company.tenant_container_id == tenant_id,
                Company.is_active.is_(True),
            )
        ).scalars()
        if can_access_data_domain(
            actor,
            tenant_container_id=tenant_id,
            domain="product_catalog",
            action="view",
            company_id=company.id,
            store_id=store.id if company.id == store.company_id else None,
        )
    ]
    if not company_ids:
        raise CatalogRuleError("You are not allowed to view the product catalog.", 403, "permission_denied")

    statement = select(CatalogProduct).where(
        CatalogProduct.tenant_container_id == tenant_id,
        CatalogProduct.company_id.in_(company_ids),
        CatalogProduct.is_active.is_(True),
    )
    normalized_search = (search or "").strip()[:100]
    if normalized_search:
        pattern = f"%{normalized_search}%"
        statement = statement.where(
            or_(
                CatalogProduct.name.ilike(pattern),
                CatalogProduct.sku.ilike(pattern),
                CatalogProduct.barcode.ilike(pattern),
                CatalogProduct.category.ilike(pattern),
            )
        )
    ordered_statement = statement.order_by(CatalogProduct.name.asc(), CatalogProduct.id.asc())
    if limit is not None:
        if limit < 1 or limit > 10001:
            raise CatalogRuleError("Product list limit must be between 1 and 10001.")
        ordered_statement = ordered_statement.limit(limit)
    products = list(db.session.execute(ordered_statement).scalars())

    can_view_inventory = can_access_data_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="inventory",
        action="view",
        company_id=store.company_id,
        store_id=store.id,
    )
    balances: dict[tuple[str, str], InventoryBalance] = {}
    if can_view_inventory and products:
        rows = db.session.execute(
            select(InventoryBalance).where(
                InventoryBalance.tenant_container_id == tenant_id,
                InventoryBalance.company_id == store.company_id,
                InventoryBalance.store_id == store.id,
                InventoryBalance.product_id.in_([product.id for product in products]),
            )
        ).scalars()
        balances = {(balance.product_owner_company_id, balance.product_id): balance for balance in rows}

    rows: list[dict] = []
    for product in products:
        balance = balances.get((product.company_id, product.id))
        rows.append(
            {
                "product": product,
                "stock_quantity": balance.quantity_on_hand if balance is not None else (0 if can_view_inventory else None),
                "low_stock_threshold": balance.low_stock_threshold if balance is not None else None,
                "is_low_stock": bool(
                    balance is not None
                    and balance.low_stock_threshold is not None
                    and balance.quantity_on_hand <= balance.low_stock_threshold
                ),
            }
        )
    return rows, store, can_view_inventory


def _money(value) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise CatalogRuleError("Price must be a valid amount.")
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise CatalogRuleError("Price must be a valid amount.") from None
    if not amount.is_finite() or amount < 0 or amount >= Decimal("100000000000"):
        raise CatalogRuleError("Price must be zero or greater and within the supported range.")
    return amount


def _expiry_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        raw = str(value).strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(raw)
                parsed = datetime.combine(parsed_date, time.min)
            except ValueError:
                raise CatalogRuleError("Expiry date must use YYYY-MM-DD or an ISO-8601 timestamp.") from None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_boolean(value, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    raise CatalogRuleError(f"{field.replace('_', ' ').title()} must be true or false.")


def _stock_threshold(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise CatalogRuleError("Low-stock threshold must be a nonnegative whole number.") from None
    if not number.is_finite() or number != number.to_integral_value() or number < 0 or number > 2147483647:
        raise CatalogRuleError("Low-stock threshold must be a nonnegative whole number.")
    return int(number)


def _product_snapshot(product: CatalogProduct) -> dict:
    return {
        "company_id": product.company_id,
        "sku": product.sku,
        "barcode": product.barcode,
        "name": product.name,
        "category": product.category,
        "price": format(product.price, ".3f") if product.price is not None else None,
        "low_stock_price": format(product.low_stock_price, ".3f") if product.low_stock_price is not None else None,
        "expiry_date": product.expiry_date.isoformat() if product.expiry_date is not None else None,
        "is_demand_notice_product": bool(product.is_demand_notice_product),
        "is_active": bool(product.is_active),
    }


def create_product(
    actor: User,
    *,
    company_id: str,
    name: str,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    price=None,
    low_stock_price=None,
    expiry_date=None,
    is_demand_notice_product=False,
    low_stock_threshold=None,
    image_url: str | None = None,
    store_id: str | None = None,
    tenant_container_id: str | None = None,
) -> CatalogProduct:
    tenant_id = _tenant_for_actor(actor, tenant_container_id)
    company = _company_in_tenant(company_id, tenant_id)
    catalog_store = _catalog_store_for_actor(
        actor,
        tenant_container_id=tenant_id,
        company_id=company.id,
        requested_store_id=store_id,
    )
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="product_catalog",
        action="add",
        company_id=company.id,
        store_id=catalog_store.id,
    )

    name = str(name or "").strip()
    sku_value = str(sku or "").strip().upper() or None
    barcode_value = str(barcode or "").strip() or None
    category_value = str(category or "").strip() or None
    image_value = str(image_url or "").strip() or None
    if not name or len(name) > 255:
        raise CatalogRuleError("Product name is required and must be 255 characters or fewer.")
    if sku_value is not None and len(sku_value) > 128:
        raise CatalogRuleError("SKU must be 128 characters or fewer.")
    if barcode_value is not None and len(barcode_value) > 128:
        raise CatalogRuleError("Barcode must be 128 characters or fewer.")
    if category_value is not None and len(category_value) > 128:
        raise CatalogRuleError("Category must be 128 characters or fewer.")
    if image_value is not None and len(image_value) > 10000:
        raise CatalogRuleError("Image URL is too long.")

    if sku_value and db.session.execute(
        select(CatalogProduct.id).where(
            CatalogProduct.tenant_container_id == tenant_id,
            CatalogProduct.company_id == company.id,
            func.upper(CatalogProduct.sku) == sku_value,
            CatalogProduct.is_active.is_(True),
        )
    ).first():
        raise CatalogRuleError("An active product with this SKU already exists in the company.", 409, "duplicate_sku")

    product_price = _money(price) if price not in (None, "") else None
    low_stock_price_value = _money(low_stock_price) if low_stock_price not in (None, "") else None
    expiry_value = _expiry_datetime(expiry_date)
    demand_notice_value = _as_boolean(is_demand_notice_product, field="is_demand_notice_product")
    threshold_value = _stock_threshold(low_stock_threshold)
    if threshold_value is not None:
        _require_domain(
            actor,
            tenant_container_id=tenant_id,
            domain="inventory",
            action="edit",
            company_id=catalog_store.company_id,
            store_id=catalog_store.id,
        )
    product = CatalogProduct(
        tenant_container_id=tenant_id,
        company_id=company.id,
        sku=sku_value,
        barcode=barcode_value,
        name=name,
        category=category_value,
        price=product_price,
        low_stock_price=low_stock_price_value,
        expiry_date=expiry_value,
        is_demand_notice_product=demand_notice_value,
        image_url=image_value,
        is_active=True,
        created_by_id=actor.id,
    )
    db.session.add(product)
    db.session.flush()
    db.session.add(
        InventoryBalance(
            tenant_container_id=tenant_id,
            company_id=company.id,
            store_id=catalog_store.id,
            product_owner_company_id=company.id,
            product_id=product.id,
            quantity_on_hand=0,
            low_stock_threshold=threshold_value,
            updated_by_id=actor.id,
        )
    )
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="catalog_product.created",
            entity_type="CatalogProduct",
            entity_id=product.id,
            after_data={**_product_snapshot(product), "low_stock_threshold": threshold_value},
        )
    )
    db.session.flush()
    return product


def update_product(
    actor: User,
    product_id: str,
    *,
    changes: dict,
    store_id: str | None = None,
    tenant_container_id: str | None = None,
) -> CatalogProduct:
    tenant_id = _tenant_for_actor(actor, tenant_container_id)
    product = _product_in_tenant(product_id, tenant_id, lock=True)
    catalog_store = _catalog_store_for_actor(
        actor,
        tenant_container_id=tenant_id,
        company_id=product.company_id,
        requested_store_id=store_id,
    )
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="product_catalog",
        action="edit",
        company_id=product.company_id,
        store_id=catalog_store.id,
    )
    if not changes:
        raise CatalogRuleError("Provide at least one product field to update.")
    before = _product_snapshot(product)
    allowed = {
        "name",
        "sku",
        "barcode",
        "category",
        "price",
        "low_stock_price",
        "expiry_date",
        "is_demand_notice_product",
        "image_url",
        "low_stock_threshold",
    }
    if set(changes) - allowed:
        raise CatalogRuleError("Unsupported product field.")
    stock_balance = None
    previous_threshold = None
    threshold_value = None
    if "low_stock_threshold" in changes:
        _require_domain(
            actor,
            tenant_container_id=tenant_id,
            domain="inventory",
            action="edit",
            company_id=catalog_store.company_id,
            store_id=catalog_store.id,
        )
        stock_balance = db.session.execute(
            select(InventoryBalance)
            .where(
                InventoryBalance.tenant_container_id == tenant_id,
                InventoryBalance.company_id == catalog_store.company_id,
                InventoryBalance.store_id == catalog_store.id,
                InventoryBalance.product_owner_company_id == product.company_id,
                InventoryBalance.product_id == product.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        previous_threshold = stock_balance.low_stock_threshold if stock_balance is not None else None
        threshold_value = _stock_threshold(changes["low_stock_threshold"])
        before["low_stock_threshold"] = previous_threshold
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        if not name or len(name) > 255:
            raise CatalogRuleError("Product name is required and must be 255 characters or fewer.")
        product.name = name
    for field_name, max_length in (("sku", 128), ("barcode", 128), ("category", 128)):
        if field_name in changes:
            value = str(changes[field_name] or "").strip() or None
            if field_name == "sku" and value is not None:
                value = value.upper()
                duplicate = db.session.execute(
                    select(CatalogProduct.id).where(
                        CatalogProduct.tenant_container_id == tenant_id,
                        CatalogProduct.company_id == product.company_id,
                        func.upper(CatalogProduct.sku) == value,
                        CatalogProduct.is_active.is_(True),
                        CatalogProduct.id != product.id,
                    )
                ).first()
                if duplicate:
                    raise CatalogRuleError("An active product with this SKU already exists in the company.", 409, "duplicate_sku")
            if value is not None and len(value) > max_length:
                raise CatalogRuleError(f"{field_name.replace('_', ' ').title()} must be {max_length} characters or fewer.")
            setattr(product, field_name, value)
    if "price" in changes:
        product.price = _money(changes["price"]) if changes["price"] not in (None, "") else None
    if "low_stock_price" in changes:
        product.low_stock_price = _money(changes["low_stock_price"]) if changes["low_stock_price"] not in (None, "") else None
    if "expiry_date" in changes:
        product.expiry_date = _expiry_datetime(changes["expiry_date"])
    if "is_demand_notice_product" in changes:
        product.is_demand_notice_product = _as_boolean(
            changes["is_demand_notice_product"],
            field="is_demand_notice_product",
        )
    if "low_stock_threshold" in changes:
        if stock_balance is None:
            stock_balance = InventoryBalance(
                tenant_container_id=tenant_id,
                company_id=catalog_store.company_id,
                store_id=catalog_store.id,
                product_owner_company_id=product.company_id,
                product_id=product.id,
                quantity_on_hand=0,
                low_stock_threshold=threshold_value,
                updated_by_id=actor.id,
            )
            db.session.add(stock_balance)
        else:
            stock_balance.low_stock_threshold = threshold_value
            stock_balance.updated_by_id = actor.id
    if "image_url" in changes:
        image_value = str(changes["image_url"] or "").strip() or None
        if image_value is not None and len(image_value) > 10000:
            raise CatalogRuleError("Image URL is too long.")
        product.image_url = image_value

    after = _product_snapshot(product)
    if "low_stock_threshold" in changes:
        after["low_stock_threshold"] = threshold_value
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=product.company_id,
            actor_user_id=actor.id,
            action="catalog_product.updated",
            entity_type="CatalogProduct",
            entity_id=product.id,
            before_data=before,
            after_data=after,
        )
    )
    db.session.flush()
    return product


def archive_product(actor: User, product_id: str, *, tenant_container_id: str | None = None) -> CatalogProduct:
    tenant_id = _tenant_for_actor(actor, tenant_container_id)
    product = _product_in_tenant(product_id, tenant_id, lock=True)
    catalog_store = _catalog_store_for_actor(
        actor,
        tenant_container_id=tenant_id,
        company_id=product.company_id,
    )
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="product_catalog",
        action="delete",
        company_id=product.company_id,
        store_id=catalog_store.id,
    )
    if not product.is_active:
        return product
    before = _product_snapshot(product)
    product.is_active = False
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=product.company_id,
            actor_user_id=actor.id,
            action="catalog_product.archived",
            entity_type="CatalogProduct",
            entity_id=product.id,
            before_data=before,
            after_data=_product_snapshot(product),
        )
    )
    db.session.flush()
    return product


def adjust_inventory(
    actor: User,
    product_id: str,
    *,
    store_id: str,
    quantity_delta,
    reason: str,
    tenant_container_id: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[InventoryBalance, InventoryMovement, RealtimeEvent | None, bool]:
    tenant_id = _tenant_for_actor(actor, tenant_container_id)
    # Serialize event creation per store on MySQL so auto-increment cursors follow
    # commit order and clients can safely replay through a later event ID.
    store = _store_in_tenant(store_id, tenant_id, lock=True)
    product = _product_in_tenant(product_id, tenant_id, lock=True)
    if not product.is_active:
        raise CatalogRuleError("Archived products cannot receive stock adjustments.", 409, "product_archived")
    if not can_access_store(
        actor,
        store.id,
        company_id=store.company_id,
        tenant_container_id=tenant_id,
    ):
        raise CatalogRuleError("You do not have access to this store.", 403, "store_forbidden")
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="product_catalog",
        action="view",
        company_id=product.company_id,
        store_id=store.id if store.company_id == product.company_id else None,
    )

    try:
        if isinstance(quantity_delta, bool):
            raise ValueError
        decimal_delta = Decimal(str(quantity_delta))
    except (InvalidOperation, ValueError, TypeError):
        raise CatalogRuleError("Stock change must be a whole number other than zero.") from None
    if (
        not decimal_delta.is_finite()
        or decimal_delta != decimal_delta.to_integral_value()
        or decimal_delta == 0
        or abs(decimal_delta) > 2147483647
    ):
        raise CatalogRuleError("Stock change must be a whole number other than zero.")
    delta = int(decimal_delta)
    action = "add" if delta > 0 else "edit"
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="inventory",
        action=action,
        company_id=store.company_id,
        store_id=store.id,
    )

    cleaned_reason = str(reason or "").strip()
    if not cleaned_reason or len(cleaned_reason) > 500:
        raise CatalogRuleError("Enter a stock-change reason of 1 to 500 characters.")
    if idempotency_key is not None:
        idempotency_key = str(idempotency_key).strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key):
            raise CatalogRuleError("Provide a valid stock-adjustment idempotency key.")
        existing = db.session.execute(
            select(InventoryMovement).where(
                InventoryMovement.tenant_container_id == tenant_id,
                InventoryMovement.actor_user_id == actor.id,
                InventoryMovement.idempotency_key == idempotency_key,
            ).with_for_update()
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.store_id != store.id
                or existing.product_id != product.id
                or existing.quantity_delta != delta
                or existing.reason != cleaned_reason
            ):
                raise CatalogRuleError("This idempotency key was already used for a different adjustment.", 409, "idempotency_conflict")
            existing_balance = db.session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_container_id == tenant_id,
                    InventoryBalance.company_id == store.company_id,
                    InventoryBalance.store_id == store.id,
                    InventoryBalance.product_owner_company_id == product.company_id,
                    InventoryBalance.product_id == product.id,
                )
            ).scalar_one_or_none()
            existing_event = None
            candidates = db.session.execute(
                select(RealtimeEvent).where(
                    RealtimeEvent.tenant_container_id == tenant_id,
                    RealtimeEvent.store_id == store.id,
                    RealtimeEvent.product_id == product.id,
                    RealtimeEvent.event_type == "inventory.updated",
                ).order_by(RealtimeEvent.id.desc()).limit(100)
            ).scalars().all()
            for candidate in candidates:
                if candidate.payload.get("movement_id") == existing.id:
                    existing_event = candidate
                    break
            return existing_balance, existing, existing_event, True

    balance_statement = select(InventoryBalance).where(
        InventoryBalance.tenant_container_id == tenant_id,
        InventoryBalance.company_id == store.company_id,
        InventoryBalance.store_id == store.id,
        InventoryBalance.product_owner_company_id == product.company_id,
        InventoryBalance.product_id == product.id,
    ).with_for_update()
    balance = db.session.execute(balance_statement).scalar_one_or_none()
    old_quantity = balance.quantity_on_hand if balance is not None else 0
    new_quantity = old_quantity + delta
    if new_quantity < 0:
        raise CatalogRuleError("Stock on hand cannot become negative.", 409, "insufficient_stock")
    if new_quantity > 2147483647:
        raise CatalogRuleError("Stock on hand exceeds the supported quantity range.")

    if balance is None:
        balance = InventoryBalance(
            tenant_container_id=tenant_id,
            company_id=store.company_id,
            store_id=store.id,
            product_owner_company_id=product.company_id,
            product_id=product.id,
            quantity_on_hand=new_quantity,
            low_stock_threshold=None,
            updated_by_id=actor.id,
        )
        db.session.add(balance)
    else:
        balance.quantity_on_hand = new_quantity
        balance.updated_by_id = actor.id

    movement = InventoryMovement(
        tenant_container_id=tenant_id,
        company_id=store.company_id,
        store_id=store.id,
        product_owner_company_id=product.company_id,
        product_id=product.id,
        movement_type="receive" if delta > 0 else "adjustment",
        quantity_delta=delta,
        reason=cleaned_reason,
        actor_user_id=actor.id,
        idempotency_key=idempotency_key,
    )
    db.session.add(movement)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=store.company_id,
            store_id=store.id,
            actor_user_id=actor.id,
            action="inventory.adjusted",
            entity_type="InventoryBalance",
            entity_id=balance.id,
            reason=cleaned_reason,
            before_data={"quantity_on_hand": old_quantity},
            after_data={"quantity_on_hand": new_quantity, "product_id": product.id, "delta": delta},
        )
    )
    db.session.flush()
    realtime_event = RealtimeEvent(
        tenant_container_id=tenant_id,
        company_id=store.company_id,
        store_id=store.id,
        product_owner_company_id=product.company_id,
        product_id=product.id,
        event_type="inventory.updated",
        payload={
            "product_id": product.id,
            "quantity_on_hand": new_quantity,
            "quantity_delta": delta,
            "movement_type": movement.movement_type,
            "movement_id": movement.id,
            "low_stock_threshold": balance.low_stock_threshold,
        },
        actor_user_id=actor.id,
    )
    db.session.add(realtime_event)
    db.session.flush()
    return balance, movement, realtime_event, False


def product_dict(product: CatalogProduct) -> dict:
    return {
        "id": product.id,
        "tenant_container_id": product.tenant_container_id,
        "company_id": product.company_id,
        "sku": product.sku,
        "barcode": product.barcode,
        "name": product.name,
        "category": product.category,
        "price": format(product.price, ".3f") if product.price is not None else None,
        "low_stock_price": format(product.low_stock_price, ".3f") if product.low_stock_price is not None else None,
        "expiry_date": product.expiry_date.isoformat() if product.expiry_date is not None else None,
        "is_demand_notice_product": bool(product.is_demand_notice_product),
        "image_url": product.image_url,
        "is_active": bool(product.is_active),
    }


def transfer_inventory(
    actor: User,
    *,
    product_id: str,
    source_store_id: str,
    destination_store_id: str,
    quantity,
    reason: str,
    tenant_container_id: str | None = None,
) -> tuple[InventoryBalance, InventoryBalance, InventoryMovement, InventoryMovement, list[RealtimeEvent]]:
    """Move stock atomically between two stores of the same legal company."""
    tenant_id = _tenant_for_actor(actor, tenant_container_id)
    if not isinstance(source_store_id, str) or not isinstance(destination_store_id, str):
        raise CatalogRuleError("Choose source and destination stores.")
    if source_store_id == destination_store_id:
        raise CatalogRuleError("Source and destination stores must be different.")

    # Lock stores in a stable order. Besides preventing two-store deadlocks, this
    # serializes event cursor creation for both store subscriptions.
    stores = list(
        db.session.execute(
            select(Store)
            .where(
                Store.tenant_container_id == tenant_id,
                Store.id.in_([source_store_id, destination_store_id]),
                Store.is_active.is_(True),
            )
            .order_by(Store.id.asc())
            .with_for_update()
        ).scalars()
    )
    store_by_id = {store.id: store for store in stores}
    source = store_by_id.get(source_store_id)
    destination = store_by_id.get(destination_store_id)
    if source is None or destination is None:
        raise CatalogRuleError("Source or destination store not found.", 404, "not_found")
    _company_in_tenant(source.company_id, tenant_id)
    _company_in_tenant(destination.company_id, tenant_id)
    if source.company_id != destination.company_id:
        raise CatalogRuleError("Stock transfers must stay within one legal company.", 403, "company_scope_forbidden")
    for store in (source, destination):
        if not can_access_store(actor, store.id, company_id=store.company_id, tenant_container_id=tenant_id):
            raise CatalogRuleError("You do not have access to both stores.", 403, "store_forbidden")

    product = _product_in_tenant(product_id, tenant_id, lock=True)
    if not product.is_active:
        raise CatalogRuleError("Archived products cannot be transferred.", 409, "product_archived")
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="product_catalog",
        action="view",
        company_id=product.company_id,
        store_id=source.id if product.company_id == source.company_id else None,
    )
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="inventory",
        action="view",
        company_id=source.company_id,
        store_id=source.id,
    )
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="inventory",
        action="view",
        company_id=destination.company_id,
        store_id=destination.id,
    )
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="inventory",
        action="edit",
        company_id=source.company_id,
        store_id=source.id,
    )
    _require_domain(
        actor,
        tenant_container_id=tenant_id,
        domain="inventory",
        action="add",
        company_id=destination.company_id,
        store_id=destination.id,
    )

    try:
        if isinstance(quantity, bool):
            raise ValueError
        parsed_quantity = Decimal(str(quantity))
    except (InvalidOperation, ValueError, TypeError):
        raise CatalogRuleError("Transfer quantity must be a positive whole number.") from None
    if (
        not parsed_quantity.is_finite()
        or parsed_quantity != parsed_quantity.to_integral_value()
        or parsed_quantity <= 0
        or parsed_quantity > 2147483647
    ):
        raise CatalogRuleError("Transfer quantity must be a positive whole number.")
    units = int(parsed_quantity)
    cleaned_reason = str(reason or "").strip()
    if not cleaned_reason or len(cleaned_reason) > 400:
        raise CatalogRuleError("Enter a transfer reason of 1 to 400 characters.")

    balances = list(
        db.session.execute(
            select(InventoryBalance)
            .where(
                InventoryBalance.tenant_container_id == tenant_id,
                InventoryBalance.company_id == source.company_id,
                InventoryBalance.store_id.in_([source.id, destination.id]),
                InventoryBalance.product_owner_company_id == product.company_id,
                InventoryBalance.product_id == product.id,
            )
            .order_by(InventoryBalance.store_id.asc())
            .with_for_update()
        ).scalars()
    )
    balance_by_store = {balance.store_id: balance for balance in balances}
    source_balance = balance_by_store.get(source.id)
    destination_balance = balance_by_store.get(destination.id)
    source_quantity = source_balance.quantity_on_hand if source_balance is not None else 0
    destination_quantity = destination_balance.quantity_on_hand if destination_balance is not None else 0
    if source_quantity < units:
        raise CatalogRuleError(
            f"Insufficient stock at {source.name}; only {source_quantity} unit(s) are available.",
            409,
            "insufficient_stock",
        )
    if destination_quantity + units > 2147483647:
        raise CatalogRuleError("Destination stock exceeds the supported quantity range.", 409, "stock_limit")

    transfer_id = str(uuid4())
    if source_balance is None:
        raise CatalogRuleError("Source stock balance is missing.", 409, "insufficient_stock")
    source_balance.quantity_on_hand = source_quantity - units
    source_balance.updated_by_id = actor.id
    if destination_balance is None:
        destination_balance = InventoryBalance(
            tenant_container_id=tenant_id,
            company_id=destination.company_id,
            store_id=destination.id,
            product_owner_company_id=product.company_id,
            product_id=product.id,
            quantity_on_hand=destination_quantity + units,
            low_stock_threshold=None,
            updated_by_id=actor.id,
        )
        db.session.add(destination_balance)
    else:
        destination_balance.quantity_on_hand = destination_quantity + units
        destination_balance.updated_by_id = actor.id

    source_reason = f"Transfer {transfer_id} to {destination.code}: {cleaned_reason}"
    destination_reason = f"Transfer {transfer_id} from {source.code}: {cleaned_reason}"
    source_movement = InventoryMovement(
        tenant_container_id=tenant_id,
        company_id=source.company_id,
        store_id=source.id,
        product_owner_company_id=product.company_id,
        product_id=product.id,
        movement_type="transfer_out",
        quantity_delta=-units,
        reason=source_reason[:500],
        actor_user_id=actor.id,
    )
    destination_movement = InventoryMovement(
        tenant_container_id=tenant_id,
        company_id=destination.company_id,
        store_id=destination.id,
        product_owner_company_id=product.company_id,
        product_id=product.id,
        movement_type="transfer_in",
        quantity_delta=units,
        reason=destination_reason[:500],
        actor_user_id=actor.id,
    )
    db.session.add_all([source_movement, destination_movement])
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=source.company_id,
            store_id=source.id,
            actor_user_id=actor.id,
            action="inventory.transferred",
            entity_type="InventoryTransfer",
            entity_id=transfer_id,
            reason=cleaned_reason,
            before_data={
                "source_quantity": source_quantity,
                "destination_quantity": destination_quantity,
            },
            after_data={
                "product_id": product.id,
                "quantity": units,
                "source_store_id": source.id,
                "source_quantity": source_balance.quantity_on_hand,
                "destination_store_id": destination.id,
                "destination_quantity": destination_balance.quantity_on_hand,
                "source_movement_id": source_movement.id,
                "destination_movement_id": destination_movement.id,
            },
        )
    )
    events = [
        RealtimeEvent(
            tenant_container_id=tenant_id,
            company_id=store.company_id,
            store_id=store.id,
            product_owner_company_id=product.company_id,
            product_id=product.id,
            event_type="inventory.updated",
            payload={
                "product_id": product.id,
                "quantity_on_hand": balance.quantity_on_hand,
                "quantity_delta": delta,
                "movement_type": movement.movement_type,
                "movement_id": movement.id,
                "transfer_id": transfer_id,
                "counterpart_store_id": counterpart.id,
            },
            actor_user_id=actor.id,
        )
        for store, balance, delta, movement, counterpart in (
            (source, source_balance, -units, source_movement, destination),
            (destination, destination_balance, units, destination_movement, source),
        )
    ]
    db.session.add_all(events)
    db.session.flush()
    return source_balance, destination_balance, source_movement, destination_movement, events


_PRODUCT_CSV_ALIASES = {
    "name": {"name", "productname", "title", "itemname"},
    "sku": {"sku", "productcode", "itemcode", "productsku"},
    "barcode": {"barcode", "barcodevalue", "bar"},
    "category": {"category", "productcategory", "type"},
    "price": {"price", "unitprice", "cost"},
    "quantity_in_stock": {"quantityinstock", "quantity", "availablequantity", "stock", "qty"},
    "expiry_date": {"expirydate", "expirationdate", "expdate", "useby"},
    "image_url": {"imageurl", "image", "picture"},
    "is_demand_notice_product": {"isdemandnoticeproduct", "isdemanditem", "dnproduct"},
    "low_stock_threshold": {"lowstockthreshold", "minstock", "threshold"},
    "low_stock_price": {"lowstockprice", "specialprice"},
}


def parse_product_csv(contents: str) -> list[dict[str, str | None]]:
    if not isinstance(contents, str) or not contents.strip():
        raise CatalogRuleError("Choose a non-empty UTF-8 CSV file.")
    try:
        reader = csv.DictReader(io.StringIO(contents, newline=""), strict=True)
        headers = reader.fieldnames or []
        normalized_headers: dict[str, str] = {}
        for header in headers:
            normalized = re.sub(r"[^a-z0-9]", "", (header or "").casefold())
            canonical = next((key for key, aliases in _PRODUCT_CSV_ALIASES.items() if normalized in aliases), None)
            if canonical is None:
                continue
            if canonical in normalized_headers:
                raise CatalogRuleError(f"CSV has multiple columns for {canonical.replace('_', ' ')}.")
            normalized_headers[canonical] = header
        if "name" not in normalized_headers or "sku" not in normalized_headers:
            raise CatalogRuleError("CSV must include Product Name and SKU/Product Code columns.")
        rows: list[dict[str, str | None]] = []
        for line_number, raw_row in enumerate(reader, start=2):
            if raw_row is None:
                continue
            extras = raw_row.get(None)
            if extras and any(str(value or "").strip() for value in extras):
                raise CatalogRuleError(f"CSV row {line_number} has more fields than the header.")
            row = {
                canonical: (raw_row.get(header) if raw_row.get(header) is not None else "")
                for canonical, header in normalized_headers.items()
            }
            if not any(str(value or "").strip() for value in row.values()):
                continue
            rows.append(row)
            if len(rows) > 1000:
                raise CatalogRuleError("CSV import is limited to 1000 product rows at a time.", 413, "csv_too_large")
    except csv.Error as error:
        raise CatalogRuleError(f"CSV could not be parsed: {error}.") from None
    if not rows:
        raise CatalogRuleError("CSV contains a header but no product rows.")
    return rows


def import_products_csv(
    actor: User,
    *,
    store_id: str,
    contents: str,
    tenant_container_id: str | None = None,
) -> tuple[dict[str, int], list[int]]:
    """Atomically import catalog rows and optional target stock quantities.

    Existing active products are matched only by company-scoped SKU. CSV product
    IDs are ignored so a file cannot select or overwrite another tenant's row.
    The caller owns the transaction and must roll back on any raised error.
    """
    rows = parse_product_csv(contents)
    tenant_id = _tenant_for_actor(actor, tenant_container_id)
    store = _store_in_tenant(store_id, tenant_id)
    if not can_access_store(actor, store.id, company_id=store.company_id, tenant_container_id=tenant_id):
        raise CatalogRuleError("You do not have access to this store.", 403, "store_forbidden")
    _company_in_tenant(store.company_id, tenant_id)

    seen_skus: set[str] = set()
    counts = {"created": 0, "updated": 0, "stock_adjustments": 0}
    event_ids: list[int] = []
    product_fields = (
        "name",
        "sku",
        "barcode",
        "category",
        "price",
        "low_stock_price",
        "expiry_date",
        "is_demand_notice_product",
        "low_stock_threshold",
        "image_url",
    )
    for line_number, row in enumerate(rows, start=2):
        try:
            sku = str(row.get("sku") or "").strip().upper()
            name = str(row.get("name") or "").strip()
            if not sku:
                raise CatalogRuleError("SKU/Product Code is required for each row.")
            if sku in seen_skus:
                raise CatalogRuleError(f"SKU {sku} appears more than once in this file.", 409, "duplicate_csv_sku")
            seen_skus.add(sku)
            if not name:
                raise CatalogRuleError("Product name is required for each row.")

            existing = db.session.execute(
                select(CatalogProduct).where(
                    CatalogProduct.tenant_container_id == tenant_id,
                    CatalogProduct.company_id == store.company_id,
                    func.upper(CatalogProduct.sku) == sku,
                    CatalogProduct.is_active.is_(True),
                ).with_for_update()
            ).scalar_one_or_none()
            field_changes = {field: row[field] for field in product_fields if field in row}
            field_changes["sku"] = sku
            # A blank threshold/stock field in an export means “not disclosed or
            # not set”; it must not silently erase store configuration.
            if not str(row.get("low_stock_threshold") or "").strip():
                field_changes.pop("low_stock_threshold", None)
            if existing is None:
                product = create_product(
                    actor,
                    company_id=store.company_id,
                    name=name,
                    sku=sku,
                    barcode=row.get("barcode"),
                    category=row.get("category"),
                    price=row.get("price"),
                    low_stock_price=row.get("low_stock_price"),
                    expiry_date=row.get("expiry_date"),
                    is_demand_notice_product=row.get("is_demand_notice_product", "false"),
                    low_stock_threshold=row.get("low_stock_threshold"),
                    image_url=row.get("image_url"),
                    store_id=store.id,
                    tenant_container_id=tenant_id,
                )
                counts["created"] += 1
            else:
                product = update_product(
                    actor,
                    existing.id,
                    changes=field_changes,
                    store_id=store.id,
                    tenant_container_id=tenant_id,
                )
                counts["updated"] += 1

            raw_target = row.get("quantity_in_stock")
            if raw_target not in (None, ""):
                target_quantity = _stock_threshold(raw_target)
                balance = db.session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_container_id == tenant_id,
                        InventoryBalance.company_id == store.company_id,
                        InventoryBalance.store_id == store.id,
                        InventoryBalance.product_owner_company_id == product.company_id,
                        InventoryBalance.product_id == product.id,
                    ).with_for_update()
                ).scalar_one_or_none()
                current_quantity = balance.quantity_on_hand if balance is not None else 0
                delta = target_quantity - current_quantity
                if delta:
                    _balance, _movement, event, _replayed = adjust_inventory(
                        actor,
                        product.id,
                        store_id=store.id,
                        quantity_delta=delta,
                        reason=f"CSV import row {line_number}: stock set to {target_quantity}",
                        tenant_container_id=tenant_id,
                    )
                    counts["stock_adjustments"] += 1
                    event_ids.append(event.id)
        except CatalogRuleError as error:
            raise CatalogRuleError(
                f"CSV row {line_number}: {error}",
                error.status_code,
                error.code,
            ) from error
    db.session.flush()
    return counts, event_ids
