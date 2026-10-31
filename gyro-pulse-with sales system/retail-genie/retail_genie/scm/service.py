"""Business rules for suppliers, purchase orders, receiving, and logistics."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage

from ..auth.store_scope import accessible_store_ids, can_access_store
from ..auth.tenant_context import current_tenant_container_id
from ..auth.tenant_policy import can_access_data_domain
from ..catalog.service import adjust_inventory
from ..extensions import db
from ..models import (
    AuditEvent,
    CatalogProduct,
    Company,
    PurchaseOrder,
    PurchaseOrderAttachment,
    PurchaseOrderItem,
    RealtimeEvent,
    Store,
    Supplier,
    SupplierAttachment,
    SupplierProduct,
    TenantContainer,
    User,
    BusinessNumberSeries,
)

PO_PREFIXES: dict[str, str] = {"purchase_order": "PO-"}
PO_ATTACHMENT_TYPES = {"invoice", "shipping", "other"}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class ScmRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _tenant_for_actor(actor: User, tenant_container_id: str | None = None) -> str:
    active_id = current_tenant_container_id(actor)
    requested_id = tenant_container_id or active_id
    if not requested_id or requested_id != active_id:
        raise ScmRuleError("Select an active tenant container first.", 403, "tenant_forbidden")
    container = db.session.get(TenantContainer, requested_id)
    if container is None or not container.is_active:
        raise ScmRuleError("Tenant container not found.", 404, "not_found")
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
        raise ScmRuleError("Company not found.", 404, "not_found")
    return company


def _store_in_tenant(store_id: str, tenant_container_id: str) -> Store:
    store = db.session.execute(
        select(Store).where(
            Store.id == store_id,
            Store.tenant_container_id == tenant_container_id,
            Store.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if store is None:
        raise ScmRuleError("Store not found.", 404, "not_found")
    return store


def _product_in_tenant(product_id: str, tenant_container_id: str, *, lock: bool = False) -> CatalogProduct:
    statement = select(CatalogProduct).where(
        CatalogProduct.id == product_id,
        CatalogProduct.tenant_container_id == tenant_container_id,
        CatalogProduct.is_active.is_(True),
    )
    if lock:
        statement = statement.with_for_update()
    product = db.session.execute(statement).scalar_one_or_none()
    if product is None:
        raise ScmRuleError("Catalog product not found.", 404, "not_found")
    return product


def _require_supplier_access(actor: User, *, tenant_container_id: str, company_id: str, action: str) -> None:
    if actor.is_super_admin:
        return
    legacy_ok = actor.has_permission("manage_suppliers")
    domain_ok = can_access_data_domain(
        actor,
        tenant_container_id=tenant_container_id,
        domain="suppliers",
        action=action,
        company_id=company_id,
    )
    if not (legacy_ok or domain_ok):
        raise ScmRuleError(f"You are not allowed to {action} suppliers.", 403, "permission_denied")


def _require_po_access(actor: User, *, tenant_container_id: str, company_id: str, action: str) -> None:
    if actor.is_super_admin:
        return
    if action in {"add", "edit", "delete"}:
        if not can_access_data_domain(
            actor,
            tenant_container_id=tenant_container_id,
            domain="inventory",
            action=action,
            company_id=company_id,
        ) and not actor.has_permission("create_pos"):
            raise ScmRuleError(f"You are not allowed to {action} purchase orders.", 403, "permission_denied")
        return
    if not can_access_data_domain(
        actor,
        tenant_container_id=tenant_container_id,
        domain="inventory",
        action="view",
        company_id=company_id,
    ):
        raise ScmRuleError("You are not allowed to view purchase orders.", 403, "permission_denied")


def _money(value, *, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ScmRuleError(f"{field} must be a number.") from None
    if not amount.is_finite() or amount < 0:
        raise ScmRuleError(f"{field} must be zero or greater.")
    return amount.quantize(Decimal("0.001"))


def _quantity(value, *, field: str) -> int:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ScmRuleError(f"{field} must be a whole number.") from None
    if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
        raise ScmRuleError(f"{field} must be a whole number.")
    quantity = int(decimal_value)
    if quantity <= 0:
        raise ScmRuleError(f"{field} must be greater than zero.")
    if quantity > 2147483647:
        raise ScmRuleError(f"{field} exceeds the supported range.")
    return quantity


def _optional_text(value, *, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ScmRuleError(f"{field} must be text.")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise ScmRuleError(f"{field} must be {maximum} characters or fewer.")
    return cleaned or None


def _valid_date(value, *, field: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        raise ScmRuleError(f"{field} must use YYYY-MM-DD format.") from None


def _po_number(company: Company) -> str:
    locked_company = db.session.execute(
        select(Company).where(
            Company.id == company.id,
            Company.tenant_container_id == company.tenant_container_id,
        ).with_for_update()
    ).scalar_one_or_none()
    if locked_company is None or not locked_company.is_active:
        raise ScmRuleError("Company not found.", 404, "not_found")
    series = db.session.execute(
        select(BusinessNumberSeries).where(
            BusinessNumberSeries.tenant_container_id == company.tenant_container_id,
            BusinessNumberSeries.company_id == company.id,
            BusinessNumberSeries.document_type == "purchase_order",
        ).with_for_update()
    ).scalar_one_or_none()
    if series is None:
        series = BusinessNumberSeries(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            document_type="purchase_order",
            prefix=PO_PREFIXES["purchase_order"],
            next_number=1,
        )
        db.session.add(series)
        db.session.flush()
    number = int(series.next_number)
    if number <= 0 or number > 999999999:
        raise ScmRuleError("Purchase order number series is exhausted; contact an administrator.", 409, "series_exhausted")
    series.next_number = number + 1
    return f"{series.prefix}{number:06d}"


# ------------------------------------------------------------------ suppliers

def supplier_dict(supplier: Supplier) -> dict:
    return {
        "id": supplier.id,
        "company_id": supplier.company_id,
        "name": supplier.name,
        "contact_email": supplier.contact_email,
        "phone": supplier.phone,
        "lead_time": supplier.lead_time,
        "notes": supplier.notes,
        "supplier_status": supplier.supplier_status,
        "created_at": supplier.created_at.isoformat().replace("+00:00", "Z") if supplier.created_at else None,
        "updated_at": supplier.updated_at.isoformat().replace("+00:00", "Z") if supplier.updated_at else None,
    }


def list_suppliers(
    actor: User,
    *,
    company_id: str | None = None,
    include_inactive: bool = False,
    search: str | None = None,
) -> list[dict]:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="view")
    statement = select(Supplier).where(
        Supplier.tenant_container_id == tenant_id,
        Supplier.company_id == company.id,
    )
    if not include_inactive:
        statement = statement.where(Supplier.supplier_status == "active")
    cleaned_search = (search or "").strip()
    if cleaned_search:
        statement = statement.where(or_(Supplier.name.ilike(f"%{cleaned_search}%"), Supplier.phone.ilike(f"%{cleaned_search}%")))
    statement = statement.order_by(Supplier.name.asc()).limit(500)
    return [supplier_dict(supplier) for supplier in db.session.execute(statement).scalars()]


def _default_company(actor: User, tenant_container_id: str) -> str:
    from ..auth.tenant_context import current_membership

    membership = current_membership(actor, tenant_container_id=tenant_container_id)
    if membership is not None and membership.company_id:
        return membership.company_id
    raise ScmRuleError("Company not found.", 404, "not_found")


def create_supplier(
    actor: User,
    *,
    company_id: str | None,
    name: str,
    contact_email: str | None = None,
    phone: str | None = None,
    lead_time: int | None = None,
    notes: str | None = None,
) -> Supplier:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="add")
    cleaned_name = _optional_text(name, field="Supplier name", maximum=160)
    if not cleaned_name:
        raise ScmRuleError("Supplier name is required.")
    cleaned_email = _optional_text(contact_email, field="Contact email", maximum=254)
    if cleaned_email and (("@" not in cleaned_email) or len(cleaned_email) > 254):
        raise ScmRuleError("Contact email must be a valid email address.")
    cleaned_phone = _optional_text(phone, field="Phone", maximum=64)
    if lead_time is not None:
        try:
            lead_time = int(lead_time)
        except (TypeError, ValueError):
            raise ScmRuleError("Lead time must be a whole number of days.") from None
        if lead_time < 0 or lead_time > 3650:
            raise ScmRuleError("Lead time must be between 0 and 3650 days.")
    supplier = Supplier(
        tenant_container_id=tenant_id,
        company_id=company.id,
        name=cleaned_name,
        contact_email=cleaned_email,
        phone=cleaned_phone,
        lead_time=lead_time,
        notes=_optional_text(notes, field="Notes", maximum=2000),
        created_by_id=actor.id,
    )
    db.session.add(supplier)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.supplier.created",
            entity_type="Supplier",
            entity_id=supplier.id,
            after_data=supplier_dict(supplier),
        )
    )
    return supplier


def _supplier_in_tenant(supplier_id: str, tenant_container_id: str, company_id: str) -> Supplier:
    supplier = db.session.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_container_id == tenant_container_id,
            Supplier.company_id == company_id,
        )
    ).scalar_one_or_none()
    if supplier is None:
        raise ScmRuleError("Supplier not found.", 404, "not_found")
    return supplier


def update_supplier(
    actor: User,
    *,
    supplier_id: str,
    company_id: str | None = None,
    changes: dict,
) -> Supplier:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    supplier = _supplier_in_tenant(supplier_id, tenant_id, company.id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="edit")
    before = supplier_dict(supplier)
    if "name" in changes:
        cleaned_name = _optional_text(changes.get("name"), field="Supplier name", maximum=160)
        if not cleaned_name:
            raise ScmRuleError("Supplier name is required.")
        supplier.name = cleaned_name
    if "contact_email" in changes:
        cleaned_email = _optional_text(changes.get("contact_email"), field="Contact email", maximum=254)
        if cleaned_email and "@" not in cleaned_email:
            raise ScmRuleError("Contact email must be a valid email address.")
        supplier.contact_email = cleaned_email
    if "phone" in changes:
        supplier.phone = _optional_text(changes.get("phone"), field="Phone", maximum=64)
    if "lead_time" in changes:
        value = changes.get("lead_time")
        if value is not None:
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ScmRuleError("Lead time must be a whole number of days.") from None
            if value < 0 or value > 3650:
                raise ScmRuleError("Lead time must be between 0 and 3650 days.")
        supplier.lead_time = value
    if "notes" in changes:
        supplier.notes = _optional_text(changes.get("notes"), field="Notes", maximum=2000)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.supplier.updated",
            entity_type="Supplier",
            entity_id=supplier.id,
            before_data=before,
            after_data=supplier_dict(supplier),
        )
    )
    return supplier


def set_supplier_status(actor: User, *, supplier_id: str, company_id: str | None = None, active: bool) -> Supplier:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    supplier = _supplier_in_tenant(supplier_id, tenant_id, company.id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="edit")
    before = supplier_dict(supplier)
    supplier.supplier_status = "active" if active else "inactive"
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.supplier.status_changed" if active else "scm.supplier.deactivated",
            entity_type="Supplier",
            entity_id=supplier.id,
            before_data=before,
            after_data=supplier_dict(supplier),
        )
    )
    return supplier


def add_supplier_attachment(actor: User, *, supplier_id: str, company_id: str | None, file_storage: FileStorage, notes: str | None = None) -> SupplierAttachment:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    supplier = _supplier_in_tenant(supplier_id, tenant_id, company.id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="edit")
    relative_path = _store_upload(file_storage, namespace=f"scm/suppliers/{supplier.id}")
    attachment = SupplierAttachment(
        tenant_container_id=tenant_id,
        company_id=company.id,
        supplier_id=supplier.id,
        file_path=relative_path,
        original_name=file_storage.filename or "attachment",
        notes=_optional_text(notes, field="Notes", maximum=500),
        uploaded_by_id=actor.id,
    )
    db.session.add(attachment)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.supplier.attachment_added",
            entity_type="SupplierAttachment",
            entity_id=attachment.id,
            after_data={"original_name": attachment.original_name, "supplier_id": supplier.id},
        )
    )
    return attachment


def list_supplier_attachments(actor: User, *, supplier_id: str, company_id: str | None = None) -> list[dict]:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    _supplier_in_tenant(supplier_id, tenant_id, company.id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="view")
    rows = db.session.execute(
        select(SupplierAttachment).where(
            SupplierAttachment.tenant_container_id == tenant_id,
            SupplierAttachment.company_id == company.id,
            SupplierAttachment.supplier_id == supplier_id,
        ).order_by(SupplierAttachment.uploaded_at.desc())
    ).scalars()
    return [
        {
            "id": row.id,
            "original_name": row.original_name,
            "notes": row.notes,
            "uploaded_at": row.uploaded_at.isoformat().replace("+00:00", "Z") if row.uploaded_at else None,
            "uploaded_by_id": row.uploaded_by_id,
        }
        for row in rows
    ]


def link_supplier_product(
    actor: User,
    *,
    supplier_id: str,
    company_id: str | None,
    product_id: str,
    unit_price,
) -> SupplierProduct:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    supplier = _supplier_in_tenant(supplier_id, tenant_id, company.id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="edit")
    product = _product_in_tenant(product_id, tenant_id, lock=True)
    price = _money(unit_price, field="Unit price")
    existing = db.session.execute(
        select(SupplierProduct).where(
            SupplierProduct.tenant_container_id == tenant_id,
            SupplierProduct.company_id == company.id,
            SupplierProduct.supplier_id == supplier.id,
            SupplierProduct.product_owner_company_id == product.company_id,
            SupplierProduct.product_id == product.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ScmRuleError("This product is already linked to the supplier.", 409, "already_linked")
    link = SupplierProduct(
        tenant_container_id=tenant_id,
        company_id=company.id,
        supplier_id=supplier.id,
        product_owner_company_id=product.company_id,
        product_id=product.id,
        unit_price=price,
        created_by_id=actor.id,
    )
    db.session.add(link)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.supplier_product.linked",
            entity_type="SupplierProduct",
            entity_id=link.id,
            after_data={"supplier_id": supplier.id, "product_id": product.id, "unit_price": str(price)},
        )
    )
    return link


def list_supplier_products(actor: User, *, supplier_id: str, company_id: str | None = None) -> list[dict]:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    _supplier_in_tenant(supplier_id, tenant_id, company.id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="view")
    rows = db.session.execute(
        select(SupplierProduct, CatalogProduct.name, CatalogProduct.sku)
        .join(
            CatalogProduct,
            (CatalogProduct.tenant_container_id == SupplierProduct.tenant_container_id)
            & (CatalogProduct.company_id == SupplierProduct.product_owner_company_id)
            & (CatalogProduct.id == SupplierProduct.product_id),
        )
        .where(
            SupplierProduct.tenant_container_id == tenant_id,
            SupplierProduct.company_id == company.id,
            SupplierProduct.supplier_id == supplier_id,
        )
        .order_by(CatalogProduct.name.asc())
    ).all()
    return [
        {
            "id": link.id,
            "supplier_id": link.supplier_id,
            "product_id": link.product_id,
            "product_name": name,
            "product_sku": sku,
            "unit_price": str(link.unit_price),
        }
        for link, name, sku in rows
    ]


def remove_supplier_product(actor: User, *, link_id: str, company_id: str | None = None) -> None:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    link = db.session.execute(
        select(SupplierProduct).where(
            SupplierProduct.tenant_container_id == tenant_id,
            SupplierProduct.company_id == company.id,
            SupplierProduct.id == link_id,
        )
    ).scalar_one_or_none()
    if link is None:
        raise ScmRuleError("Supplier product link not found.", 404, "not_found")
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="delete")
    db.session.delete(link)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.supplier_product.removed",
            entity_type="SupplierProduct",
            entity_id=link.id,
            before_data={"supplier_id": link.supplier_id, "product_id": link.product_id},
        )
    )


def _store_upload(file_storage: FileStorage, *, namespace: str) -> str:
    """Persist an uploaded file under the private tenant uploads directory."""
    if file_storage is None or not getattr(file_storage, "filename", None):
        raise ScmRuleError("Choose a file to attach.")
    original_name = os.path.basename(file_storage.filename.replace("\\", "/"))
    if not original_name or len(original_name) > 255:
        raise ScmRuleError("The file name must be 1-255 characters.")
    if ".." in original_name or original_name.startswith("."):
        raise ScmRuleError("Unsafe file names are not allowed.")
    size = 0
    stream = file_storage.stream
    try:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(0)
    except (AttributeError, OSError, ValueError):
        size = len(file_storage.read() or b"")
        file_storage.stream.seek(0)
    if size <= 0 or size > MAX_ATTACHMENT_BYTES:
        raise ScmRuleError("Attached files must be between 1 byte and 10 MB.")
    digest_prefix = uuid4().hex[:12]
    relative_path = f"{namespace}/{digest_prefix}_{original_name}"
    from flask import current_app

    destination = os.path.join(current_app.config["UPLOADS_DIR"], relative_path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    file_storage.save(destination)
    return relative_path


# ------------------------------------------------------------ purchase orders

def purchase_order_dict(po: PurchaseOrder, *, include_items: bool = True) -> dict:
    data = {
        "id": po.id,
        "company_id": po.company_id,
        "po_number": po.po_number,
        "supplier_id": po.supplier_id,
        "status": po.status,
        "total_amount": str(po.total_amount),
        "advance_paid": str(po.advance_paid),
        "deadline": po.deadline.isoformat() if po.deadline else None,
        "expected_delivery": po.expected_delivery.isoformat() if po.expected_delivery else None,
        "transportation_details": po.transportation_details,
        "logistics_status": po.logistics_status,
        "received_store_id": po.received_store_id,
        "created_at": po.created_at.isoformat().replace("+00:00", "Z") if po.created_at else None,
        "updated_at": po.updated_at.isoformat().replace("+00:00", "Z") if po.updated_at else None,
        "confirmed_at": po.confirmed_at.isoformat().replace("+00:00", "Z") if po.confirmed_at else None,
        "completed_at": po.completed_at.isoformat().replace("+00:00", "Z") if po.completed_at else None,
    }
    if include_items:
        items = db.session.execute(
            select(PurchaseOrderItem).where(
                PurchaseOrderItem.tenant_container_id == po.tenant_container_id,
                PurchaseOrderItem.company_id == po.company_id,
                PurchaseOrderItem.po_id == po.id,
            ).order_by(PurchaseOrderItem.created_at.asc())
        ).scalars()
        data["items"] = [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_owner_company_id": item.product_owner_company_id,
                "quantity_ordered": item.quantity_ordered,
                "quantity_received": item.quantity_received,
                "unit_price": str(item.unit_price),
                "notes": item.notes,
            }
            for item in items
        ]
        attachments = db.session.execute(
            select(PurchaseOrderAttachment).where(
                PurchaseOrderAttachment.tenant_container_id == po.tenant_container_id,
                PurchaseOrderAttachment.company_id == po.company_id,
                PurchaseOrderAttachment.po_id == po.id,
            ).order_by(PurchaseOrderAttachment.uploaded_at.desc())
        ).scalars()
        data["attachments"] = [
            {
                "id": attachment.id,
                "original_name": attachment.original_name,
                "attachment_type": attachment.attachment_type,
                "notes": attachment.notes,
                "uploaded_at": attachment.uploaded_at.isoformat().replace("+00:00", "Z") if attachment.uploaded_at else None,
            }
            for attachment in attachments
        ]
    return data


def list_purchase_orders(
    actor: User,
    *,
    company_id: str | None = None,
    status: str | None = None,
    supplier_id: str | None = None,
    search: str | None = None,
) -> list[dict]:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    _require_po_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="view")
    statement = select(PurchaseOrder).where(
        PurchaseOrder.tenant_container_id == tenant_id,
        PurchaseOrder.company_id == company.id,
    )
    if status:
        if status not in {"draft", "confirmed", "partially_received", "received", "cancelled"}:
            raise ScmRuleError("Unknown purchase order status.")
        statement = statement.where(PurchaseOrder.status == status)
    if supplier_id:
        statement = statement.where(PurchaseOrder.supplier_id == supplier_id)
    cleaned_search = (search or "").strip()
    if cleaned_search:
        statement = statement.where(PurchaseOrder.po_number.ilike(f"%{cleaned_search}%"))
    statement = statement.order_by(PurchaseOrder.created_at.desc()).limit(500)
    return [purchase_order_dict(po, include_items=False) for po in db.session.execute(statement).scalars()]


def _po_in_tenant(po_id: str, tenant_container_id: str, company_id: str, *, lock: bool = False) -> PurchaseOrder:
    statement = select(PurchaseOrder).where(
        PurchaseOrder.id == po_id,
        PurchaseOrder.tenant_container_id == tenant_container_id,
        PurchaseOrder.company_id == company_id,
    )
    if lock:
        statement = statement.with_for_update()
    po = db.session.execute(statement).scalar_one_or_none()
    if po is None:
        raise ScmRuleError("Purchase order not found.", 404, "not_found")
    return po


def _po_item(po: PurchaseOrder, item_id: str, *, lock: bool = False) -> PurchaseOrderItem:
    statement = select(PurchaseOrderItem).where(
        PurchaseOrderItem.id == item_id,
        PurchaseOrderItem.tenant_container_id == po.tenant_container_id,
        PurchaseOrderItem.company_id == po.company_id,
        PurchaseOrderItem.po_id == po.id,
    )
    if lock:
        statement = statement.with_for_update()
    item = db.session.execute(statement).scalar_one_or_none()
    if item is None:
        raise ScmRuleError("Purchase order item not found.", 404, "not_found")
    return item


def create_purchase_order(
    actor: User,
    *,
    company_id: str | None,
    supplier_id: str,
    items: list[dict],
    expected_delivery: date | str | None = None,
    deadline: date | str | None = None,
    transportation_details: str | None = None,
    advance_paid=None,
) -> PurchaseOrder:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    _require_po_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="add")
    supplier = _supplier_in_tenant(supplier_id, tenant_id, company.id)
    if supplier.supplier_status != "active":
        raise ScmRuleError("This supplier is deactivated.", 409, "supplier_inactive")
    if not isinstance(items, list) or not items or len(items) > 200:
        raise ScmRuleError("Provide 1-200 purchase order lines.")
    total = Decimal("0.000")
    line_payloads: list[dict] = []
    seen_products: set[tuple[str, str]] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ScmRuleError("Each purchase order line must be an object.")
        product_id = raw.get("product_id")
        product = _product_in_tenant(str(product_id), tenant_id)
        key = (product.company_id, product.id)
        if key in seen_products:
            raise ScmRuleError(f"Duplicate product line: {product.name}")
        seen_products.add(key)
        quantity = _quantity(raw.get("quantity"), field="Quantity")
        unit_price = _money(raw.get("unit_price"), field="Unit price")
        if unit_price <= 0:
            raise ScmRuleError("Unit price must be greater than zero.")
        line_payloads.append(
            {
                "product_owner_company_id": product.company_id,
                "product_id": product.id,
                "quantity_ordered": quantity,
                "unit_price": unit_price,
                "notes": _optional_text(raw.get("notes"), field="Line notes", maximum=500),
            }
        )
        total += unit_price * quantity
    advance = _money(advance_paid or 0, field="Advance paid")
    if advance > total:
        raise ScmRuleError("Advance paid cannot exceed the purchase order total.")
    po = PurchaseOrder(
        tenant_container_id=tenant_id,
        company_id=company.id,
        po_number=_po_number(company),
        supplier_id=supplier.id,
        status="draft",
        total_amount=total,
        advance_paid=advance,
        deadline=_valid_date(deadline, field="Deadline"),
        expected_delivery=_valid_date(expected_delivery, field="Expected delivery"),
        transportation_details=_optional_text(transportation_details, field="Transportation details", maximum=2000),
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(po)
    db.session.flush()
    for payload in line_payloads:
        db.session.add(
            PurchaseOrderItem(
                tenant_container_id=tenant_id,
                company_id=company.id,
                po_id=po.id,
                **payload,
            )
        )
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.purchase_order.created",
            entity_type="PurchaseOrder",
            entity_id=po.id,
            after_data=purchase_order_dict(po, include_items=False),
        )
    )
    return po


def update_purchase_order(
    actor: User,
    *,
    po_id: str,
    company_id: str | None = None,
    changes: dict,
) -> PurchaseOrder:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    po = _po_in_tenant(po_id, tenant_id, company.id, lock=True)
    _require_po_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="edit")
    if po.status != "draft":
        raise ScmRuleError("Only draft purchase orders can be edited.", 409, "not_draft")
    before = purchase_order_dict(po, include_items=False)
    if "supplier_id" in changes and changes.get("supplier_id"):
        supplier = _supplier_in_tenant(str(changes.get("supplier_id")), tenant_id, company.id)
        if supplier.supplier_status != "active":
            raise ScmRuleError("This supplier is deactivated.", 409, "supplier_inactive")
        po.supplier_id = supplier.id
    if "expected_delivery" in changes:
        po.expected_delivery = _valid_date(changes.get("expected_delivery"), field="Expected delivery")
    if "deadline" in changes:
        po.deadline = _valid_date(changes.get("deadline"), field="Deadline")
    if "transportation_details" in changes:
        po.transportation_details = _optional_text(changes.get("transportation_details"), field="Transportation details", maximum=2000)
    if "advance_paid" in changes:
        advance = _money(changes.get("advance_paid") or 0, field="Advance paid")
        if advance > po.total_amount:
            raise ScmRuleError("Advance paid cannot exceed the purchase order total.")
        po.advance_paid = advance
    if "items" in changes:
        new_items = changes.get("items")
        if not isinstance(new_items, list) or not new_items or len(new_items) > 200:
            raise ScmRuleError("Provide 1-200 purchase order lines.")
        total = Decimal("0.000")
        db.session.execute(
            delete(PurchaseOrderItem).where(
                PurchaseOrderItem.tenant_container_id == tenant_id,
                PurchaseOrderItem.company_id == company.id,
                PurchaseOrderItem.po_id == po.id,
            )
        )
        seen_products: set[tuple[str, str]] = set()
        for raw in new_items:
            if not isinstance(raw, dict):
                raise ScmRuleError("Each purchase order line must be an object.")
            product = _product_in_tenant(str(raw.get("product_id")), tenant_id)
            key = (product.company_id, product.id)
            if key in seen_products:
                raise ScmRuleError(f"Duplicate product line: {product.name}")
            seen_products.add(key)
            quantity = _quantity(raw.get("quantity"), field="Quantity")
            unit_price = _money(raw.get("unit_price"), field="Unit price")
            if unit_price <= 0:
                raise ScmRuleError("Unit price must be greater than zero.")
            db.session.add(
                PurchaseOrderItem(
                    tenant_container_id=tenant_id,
                    company_id=company.id,
                    po_id=po.id,
                    product_owner_company_id=product.company_id,
                    product_id=product.id,
                    quantity_ordered=quantity,
                    unit_price=unit_price,
                    notes=_optional_text(raw.get("notes"), field="Line notes", maximum=500),
                )
            )
            total += unit_price * quantity
        po.total_amount = total
        advance = _money(changes.get("advance_paid", po.advance_paid), field="Advance paid")
        if advance > total:
            raise ScmRuleError("Advance paid cannot exceed the purchase order total.")
        po.advance_paid = advance
    po.updated_by_id = actor.id
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.purchase_order.updated",
            entity_type="PurchaseOrder",
            entity_id=po.id,
            before_data=before,
            after_data=purchase_order_dict(po, include_items=False),
        )
    )
    return po


def confirm_purchase_order(actor: User, *, po_id: str, company_id: str | None = None) -> PurchaseOrder:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    po = _po_in_tenant(po_id, tenant_id, company.id, lock=True)
    if not (actor.is_super_admin or actor.has_permission("approve_pos")):
        raise ScmRuleError("Only an approver can confirm a purchase order.", 403, "permission_denied")
    if po.status != "draft":
        raise ScmRuleError("Only draft purchase orders can be confirmed.", 409, "not_draft")
    before = purchase_order_dict(po, include_items=False)
    po.status = "confirmed"
    po.confirmed_at = datetime.now(po.created_at.tzinfo) if po.created_at else datetime.utcnow()
    po.updated_by_id = actor.id
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.purchase_order.confirmed",
            entity_type="PurchaseOrder",
            entity_id=po.id,
            before_data=before,
            after_data=purchase_order_dict(po, include_items=False),
        )
    )
    return po


def cancel_purchase_order(actor: User, *, po_id: str, company_id: str | None = None, reason: str | None = None) -> PurchaseOrder:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    po = _po_in_tenant(po_id, tenant_id, company.id, lock=True)
    _require_po_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="edit")
    if po.status in {"received", "cancelled"}:
        raise ScmRuleError(f"A {po.status} purchase order cannot be cancelled.", 409, "invalid_status")
    cleaned_reason = _optional_text(reason, field="Cancellation reason", maximum=500) or "Cancelled by administrator"
    before = purchase_order_dict(po, include_items=False)
    po.status = "cancelled"
    po.updated_by_id = actor.id
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.purchase_order.cancelled",
            entity_type="PurchaseOrder",
            entity_id=po.id,
            reason=cleaned_reason,
            before_data=before,
            after_data=purchase_order_dict(po, include_items=False),
        )
    )
    return po


def receive_purchase_order(
    actor: User,
    *,
    po_id: str,
    company_id: str | None = None,
    receipts: list[dict],
) -> PurchaseOrder:
    """Receive one or more lines into a store; stock and audit trail update together."""
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    po = _po_in_tenant(po_id, tenant_id, company.id, lock=True)
    if po.status in {"draft", "received", "cancelled"}:
        raise ScmRuleError(f"A {po.status} purchase order cannot receive stock.", 409, "invalid_status")
    if not (actor.is_super_admin or actor.has_permission("receive_stock")):
        raise ScmRuleError("Stock receiving requires the receive_stock permission.", 403, "permission_denied")
    if not isinstance(receipts, list) or not receipts or len(receipts) > 200:
        raise ScmRuleError("Provide 1-200 receipt lines.")
    before = purchase_order_dict(po)
    applied: list[dict] = []
    realtime_event_ids: list[int] = []
    for raw in receipts:
        if not isinstance(raw, dict):
            raise ScmRuleError("Each receipt line must be an object.")
        item = _po_item(po, str(raw.get("item_id")), lock=True)
        quantity = _quantity(raw.get("quantity"), field="Received quantity")
        if item.quantity_received + quantity > item.quantity_ordered:
            raise ScmRuleError(
                f"Cannot receive more than the ordered quantity for item {item.id}.",
                409,
                "receipt_exceeds_order",
            )
        store_id = str(raw.get("store_id", ""))
        store = _store_in_tenant(store_id, tenant_id)
        if store.company_id != company.id:
            raise ScmRuleError("Receiving stores must belong to the purchase order's company.", 403, "store_forbidden")
        if not can_access_store(actor, store.id, company_id=company.id, tenant_container_id=tenant_id):
            raise ScmRuleError("You do not have access to the receiving store.", 403, "store_forbidden")
        # adjust_inventory validates inventory permissions, locks the product
        # row, writes the movement, audit entry, and realtime event.
        _balance, _movement, inventory_event, _replayed = adjust_inventory(
            actor,
            item.product_id,
            store_id=store.id,
            quantity_delta=quantity,
            reason=f"purchase_order:{po.po_number}",
            tenant_container_id=tenant_id,
        )
        realtime_event_ids.append(inventory_event.id)
        item.quantity_received += quantity
        applied.append({"item_id": item.id, "quantity": quantity, "store_id": store.id})
    if all(item.quantity_received >= item.quantity_ordered for item in _po_items(po)):
        po.status = "received"
        po.completed_at = datetime.now(po.created_at.tzinfo) if po.created_at else datetime.utcnow()
    else:
        po.status = "partially_received"
    if applied:
        po.received_store_id = applied[-1]["store_id"]
    po.updated_by_id = actor.id
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.purchase_order.received",
            entity_type="PurchaseOrder",
            entity_id=po.id,
            reason=f"Received {sum(line['quantity'] for line in applied)} unit(s).",
            before_data=before,
            after_data=purchase_order_dict(po),
        )
    )
    quantities_by_store: dict[str, int] = {}
    for receipt in applied:
        quantities_by_store[receipt["store_id"]] = quantities_by_store.get(receipt["store_id"], 0) + receipt["quantity"]
    for receipt_store_id, quantity_total in quantities_by_store.items():
        realtime_event = RealtimeEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            store_id=receipt_store_id,
            domain="inventory",
            event_type="scm.purchase_order.received",
            payload={"purchase_order_id": po.id, "po_number": po.po_number, "quantity_received": quantity_total, "status": po.status},
            actor_user_id=actor.id,
        )
        db.session.add(realtime_event)
        db.session.flush()
        realtime_event_ids.append(realtime_event.id)
    po._realtime_event_ids = realtime_event_ids
    return po


def _po_items(po: PurchaseOrder) -> list[PurchaseOrderItem]:
    return list(
        db.session.execute(
            select(PurchaseOrderItem).where(
                PurchaseOrderItem.tenant_container_id == po.tenant_container_id,
                PurchaseOrderItem.company_id == po.company_id,
                PurchaseOrderItem.po_id == po.id,
            )
        )
        .scalars()
    )


def update_purchase_order_logistics(
    actor: User,
    *,
    po_id: str,
    company_id: str | None = None,
    logistics_status: str | None,
    transportation_details: str | None = None,
) -> PurchaseOrder:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    po = _po_in_tenant(po_id, tenant_id, company.id, lock=True)
    if po.status == "cancelled":
        raise ScmRuleError("A cancelled purchase order cannot be updated.", 409, "invalid_status")
    if not (actor.is_super_admin or actor.has_permission("manage_logistics")):
        raise ScmRuleError("Logistics updates require the manage_logistics permission.", 403, "permission_denied")
    before = purchase_order_dict(po, include_items=False)
    cleaned_status = _optional_text(logistics_status, field="Logistics status", maximum=120)
    if cleaned_status is None:
        raise ScmRuleError("Logistics status is required.")
    po.logistics_status = cleaned_status
    if transportation_details is not None:
        po.transportation_details = _optional_text(transportation_details, field="Transportation details", maximum=2000)
    po.updated_by_id = actor.id
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.purchase_order.logistics_updated",
            entity_type="PurchaseOrder",
            entity_id=po.id,
            before_data=before,
            after_data=purchase_order_dict(po, include_items=False),
        )
    )
    return po


def add_po_attachment(
    actor: User,
    *,
    po_id: str,
    company_id: str | None,
    file_storage: FileStorage,
    attachment_type: str = "other",
    notes: str | None = None,
) -> PurchaseOrderAttachment:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    po = _po_in_tenant(po_id, tenant_id, company.id)
    _require_po_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="edit")
    if attachment_type not in PO_ATTACHMENT_TYPES:
        raise ScmRuleError("Unknown attachment type.")
    relative_path = _store_upload(file_storage, namespace=f"scm/purchase-orders/{po.id}")
    attachment = PurchaseOrderAttachment(
        tenant_container_id=tenant_id,
        company_id=company.id,
        po_id=po.id,
        file_path=relative_path,
        original_name=file_storage.filename or "attachment",
        attachment_type=attachment_type,
        notes=_optional_text(notes, field="Notes", maximum=500),
        uploaded_by_id=actor.id,
    )
    db.session.add(attachment)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action="scm.purchase_order.attachment_added",
            entity_type="PurchaseOrderAttachment",
            entity_id=attachment.id,
            after_data={"original_name": attachment.original_name, "po_id": po.id, "attachment_type": attachment_type},
        )
    )
    return attachment


def get_po_attachment(actor: User, *, po_id: str, attachment_id: str, company_id: str | None = None) -> PurchaseOrderAttachment:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    po = _po_in_tenant(po_id, tenant_id, company.id)
    _require_po_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="view")
    attachment = db.session.execute(select(PurchaseOrderAttachment).where(
        PurchaseOrderAttachment.id == attachment_id,
        PurchaseOrderAttachment.tenant_container_id == tenant_id,
        PurchaseOrderAttachment.company_id == company.id,
        PurchaseOrderAttachment.po_id == po.id,
    )).scalar_one_or_none()
    if attachment is None:
        raise ScmRuleError("Purchase-order attachment not found.", 404, "not_found")
    return attachment


def get_supplier_attachment(actor: User, *, supplier_id: str, attachment_id: str, company_id: str | None = None) -> SupplierAttachment:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id or _default_company(actor, tenant_id), tenant_id)
    _supplier_in_tenant(supplier_id, tenant_id, company.id)
    _require_supplier_access(actor, tenant_container_id=tenant_id, company_id=company.id, action="view")
    attachment = db.session.execute(select(SupplierAttachment).where(
        SupplierAttachment.id == attachment_id,
        SupplierAttachment.tenant_container_id == tenant_id,
        SupplierAttachment.company_id == company.id,
        SupplierAttachment.supplier_id == supplier_id,
    )).scalar_one_or_none()
    if attachment is None:
        raise ScmRuleError("Supplier attachment not found.", 404, "not_found")
    return attachment
