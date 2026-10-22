"""Stock count audits: creation, conduct, evidence, and variance posting."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from flask import current_app
from sqlalchemy import func, select

from ..auth.store_scope import can_access_store
from ..auth.tenant_context import current_tenant_container_id
from ..catalog.service import CatalogRuleError, adjust_inventory
from ..extensions import db
from ..models import (
    AuditEvent,
    CatalogProduct,
    Company,
    InventoryMovement,
    StockAudit,
    StockAuditImage,
    StockAuditItem,
    StockAuditItemCount,
    Store,
    TenantContainer,
    User,
)

MAX_EVIDENCE_BYTES = 5 * 1024 * 1024


class StockAuditRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _tenant_for_actor(actor: User) -> str:
    tenant_id = current_tenant_container_id(actor)
    if not tenant_id:
        raise StockAuditRuleError("Select an active tenant container first.", 403, "tenant_forbidden")
    container = db.session.get(TenantContainer, tenant_id)
    if container is None or not container.is_active:
        raise StockAuditRuleError("Tenant container not found.", 404, "not_found")
    return tenant_id


def _company_in_tenant(company_id: str | None, tenant_container_id: str, actor: User) -> Company:
    if actor.is_super_admin:
        company = db.session.get(Company, company_id) if company_id else None
    else:
        from ..auth.tenant_context import current_membership

        membership = current_membership(actor, tenant_container_id=tenant_container_id)
        company = db.session.get(Company, membership.company_id) if membership and membership.company_id else None
        if company is not None and company_id and company_id != company.id:
            company = None
    if company is None or company.tenant_container_id != tenant_container_id or not company.is_active:
        raise StockAuditRuleError("Company not found.", 404, "not_found")
    return company


def _require_manage_audits(actor: User, *, tenant_container_id: str, company_id: str, action: str = "edit") -> None:
    if actor.is_super_admin:
        return
    if actor.has_permission("manage_audits"):
        return
    from ..auth.tenant_policy import can_access_data_domain

    if not can_access_data_domain(
        actor,
        tenant_container_id=tenant_container_id,
        domain="audit",
        action=action,
        company_id=company_id,
    ):
        raise StockAuditRuleError(f"You are not allowed to {action} stock audits.", 403, "permission_denied")


def _audit_number(company: Company) -> str:
    locked = db.session.execute(
        select(Company).where(
            Company.id == company.id,
            Company.tenant_container_id == company.tenant_container_id,
        ).with_for_update()
    ).scalar_one_or_none()
    if locked is None or not locked.is_active:
        raise StockAuditRuleError("Company not found.", 404, "not_found")
    max_number = db.session.execute(
        select(func.count(StockAudit.id)).where(
            StockAudit.tenant_container_id == company.tenant_container_id,
            StockAudit.company_id == company.id,
        )
    ).scalar_one_or_none() or 0
    return f"AUD-{int(max_number) + 1:06d}"


def audit_dict(audit: StockAudit, *, include_items: bool = True) -> dict:
    data = {
        "id": audit.id,
        "company_id": audit.company_id,
        "store_id": audit.store_id,
        "audit_number": audit.audit_number,
        "title": audit.title,
        "store_location": audit.store_location,
        "admin_id": audit.admin_id,
        "auditor_id": audit.auditor_id,
        "status": audit.status,
        "started_at": audit.started_at.isoformat().replace("+00:00", "Z") if audit.started_at else None,
        "completed_at": audit.completed_at.isoformat().replace("+00:00", "Z") if audit.completed_at else None,
        "created_at": audit.created_at.isoformat().replace("+00:00", "Z") if audit.created_at else None,
    }
    if include_items:
        items = list(db.session.execute(
            select(StockAuditItem).where(
                StockAuditItem.tenant_container_id == audit.tenant_container_id,
                StockAuditItem.company_id == audit.company_id,
                StockAuditItem.audit_id == audit.id,
            ).order_by(StockAuditItem.created_at.asc())
        ).scalars())
        latest_counts = {}
        if items:
            count_rows = db.session.execute(
                select(StockAuditItemCount.audit_item_id, StockAuditItemCount.id, StockAuditItemCount.count)
                .where(
                    StockAuditItemCount.tenant_container_id == audit.tenant_container_id,
                    StockAuditItemCount.audit_item_id.in_([item.id for item in items]),
                ).order_by(StockAuditItemCount.created_at.desc())
            ).all()
            for item_id, count_id, count_value in count_rows:
                latest_counts.setdefault(item_id, {"id": count_id, "count": count_value})
        data["items"] = [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "product_sku": item.product_sku,
                "current_stock": item.current_stock,
                "final_audited_qty": item.final_audited_qty,
                "latest_count_event_id": latest_counts.get(item.id, {}).get("id"),
                "latest_count": latest_counts.get(item.id, {}).get("count"),
                "notes": item.notes,
            }
            for item in items
        ]
    return data


def create_stock_audit(
    actor: User,
    *,
    company_id: str | None,
    store_id: str,
    title: str,
    product_ids: list[str] | None = None,
    store_location: str | None = None,
    auditor_id: str | None = None,
) -> StockAudit:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id, tenant_id, actor)
    _require_manage_audits(actor, tenant_container_id=tenant_id, company_id=company.id, action="add")
    store = db.session.execute(
        select(Store).where(
            Store.id == store_id,
            Store.tenant_container_id == tenant_id,
            Store.company_id == company.id,
            Store.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if store is None:
        raise StockAuditRuleError("Store not found.", 404, "not_found")
    cleaned_title = str(title or "").strip()
    if not cleaned_title or len(cleaned_title) > 160:
        raise StockAuditRuleError("A title of 1-160 characters is required.")
    statement = select(CatalogProduct).where(
        CatalogProduct.tenant_container_id == tenant_id,
        CatalogProduct.company_id == company.id,
        CatalogProduct.is_active.is_(True),
    )
    if product_ids:
        if len(product_ids) > 500:
            raise StockAuditRuleError("An audit can cover at most 500 products.")
        statement = statement.where(CatalogProduct.id.in_(product_ids))
    products = list(db.session.execute(statement.order_by(CatalogProduct.name.asc())).scalars())
    if not products:
        raise StockAuditRuleError("Select at least one in-stock catalog product.")
    audit = StockAudit(
        tenant_container_id=tenant_id,
        company_id=company.id,
        store_id=store.id,
        audit_number=_audit_number(company),
        title=cleaned_title,
        store_location=(store_location or "").strip()[:160] or None,
        admin_id=actor.id if not actor.is_super_admin else actor.id,
        auditor_id=auditor_id or None,
        status="draft",
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(audit)
    db.session.flush()
    for product in products:
        balance = db.session.execute(
            select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(
                InventoryMovement.tenant_container_id == tenant_id,
                InventoryMovement.store_id == store.id,
                InventoryMovement.product_owner_company_id == product.company_id,
                InventoryMovement.product_id == product.id,
            )
        ).scalar_one_or_none()
        current_stock = int(balance or 0)
        db.session.add(
            StockAuditItem(
                tenant_container_id=tenant_id,
                company_id=company.id,
                audit_id=audit.id,
                product_owner_company_id=product.company_id,
                product_id=product.id,
                product_name=product.name,
                product_sku=product.sku,
                current_stock=current_stock,
            )
        )
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=tenant_id,
            company_id=company.id,
            store_id=store.id,
            actor_user_id=actor.id,
            action="audit.stock.created",
            entity_type="StockAudit",
            entity_id=audit.id,
            after_data=audit_dict(audit, include_items=False),
        )
    )
    return audit


def _audit_for_actor(actor: User, audit_id: str, *, company_id: str | None = None, lock: bool = False) -> StockAudit:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id, tenant_id, actor)
    statement = select(StockAudit).where(
        StockAudit.id == audit_id,
        StockAudit.tenant_container_id == tenant_id,
        StockAudit.company_id == company.id,
    )
    if lock:
        statement = statement.with_for_update()
    audit = db.session.execute(statement).scalar_one_or_none()
    if audit is None:
        raise StockAuditRuleError("Stock audit not found.", 404, "not_found")
    return audit


def list_stock_audits(actor: User, *, company_id: str | None = None, status: str | None = None, store_id: str | None = None) -> list[dict]:
    tenant_id = _tenant_for_actor(actor)
    company = _company_in_tenant(company_id, tenant_id, actor)
    _require_manage_audits(actor, tenant_container_id=tenant_id, company_id=company.id, action="view")
    statement = select(StockAudit).where(
        StockAudit.tenant_container_id == tenant_id,
        StockAudit.company_id == company.id,
    )
    if status:
        if status not in {"draft", "in_progress", "completed", "cancelled"}:
            raise StockAuditRuleError("Unknown audit status.")
        statement = statement.where(StockAudit.status == status)
    if store_id:
        statement = statement.where(StockAudit.store_id == store_id)
    statement = statement.order_by(StockAudit.created_at.desc()).limit(500)
    return [audit_dict(audit, include_items=False) for audit in db.session.execute(statement).scalars()]


def start_stock_audit(actor: User, *, audit_id: str, company_id: str | None = None, auditor_id: str | None = None, auditor_selfie_path: str | None = None) -> StockAudit:
    audit = _audit_for_actor(actor, audit_id, company_id=company_id, lock=True)
    _require_manage_audits(actor, tenant_container_id=audit.tenant_container_id, company_id=audit.company_id, action="edit")
    if audit.status != "draft":
        raise StockAuditRuleError(f"A {audit.status} audit cannot be started.", 409, "invalid_status")
    if auditor_id:
        assigned = db.session.execute(
            select(User.id).where(User.id == auditor_id, User.is_active.is_(True))
        ).scalar_one_or_none()
        if assigned is None:
            raise StockAuditRuleError("The assigned auditor account does not exist.", 404, "not_found")
        audit.auditor_id = auditor_id
    before = audit_dict(audit, include_items=False)
    audit.status = "in_progress"
    audit.started_at = datetime.now(timezone.utc)
    if auditor_selfie_path:
        audit.auditor_selfie_path = auditor_selfie_path
    audit.updated_by_id = actor.id
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=audit.tenant_container_id,
            company_id=audit.company_id,
            store_id=audit.store_id,
            actor_user_id=actor.id,
            action="audit.stock.started",
            entity_type="StockAudit",
            entity_id=audit.id,
            before_data=before,
            after_data=audit_dict(audit, include_items=False),
        )
    )
    return audit


def _conductor_check(actor: User, audit: StockAudit) -> None:
    if actor.is_super_admin or actor.is_admin:
        return
    if not actor.has_permission("conduct_audits"):
        raise StockAuditRuleError("Only an assigned auditor can conduct this audit.", 403, "permission_denied")
    if audit.auditor_id and str(audit.auditor_id) != str(actor.id):
        raise StockAuditRuleError("This audit is assigned to another auditor.", 403, "permission_denied")


def record_count(actor: User, *, audit_id: str, item_id: str, company_id: str | None = None, count, notes: str | None = None) -> StockAuditItemCount:
    audit = _audit_for_actor(actor, audit_id, company_id=company_id, lock=True)
    if audit.status != "in_progress":
        raise StockAuditRuleError(f"A {audit.status} audit cannot record counts.", 409, "invalid_status")
    _conductor_check(actor, audit)
    item = db.session.execute(
        select(StockAuditItem).where(
            StockAuditItem.id == item_id,
            StockAuditItem.tenant_container_id == audit.tenant_container_id,
            StockAuditItem.company_id == audit.company_id,
            StockAuditItem.audit_id == audit.id,
        )
    ).scalar_one_or_none()
    if item is None:
        raise StockAuditRuleError("Audit item not found.", 404, "not_found")
    try:
        counted = int(count)
    except (TypeError, ValueError):
        raise StockAuditRuleError("The count must be a whole number.") from None
    if counted < 0:
        raise StockAuditRuleError("The count cannot be negative.")
    cleaned_notes = (str(notes or "").strip()[:500]) or None
    count_event = StockAuditItemCount(
        tenant_container_id=audit.tenant_container_id,
        company_id=audit.company_id,
        audit_item_id=item.id,
        count=counted,
        notes=cleaned_notes,
        counted_by_id=actor.id,
    )
    db.session.add(count_event)
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=audit.tenant_container_id,
            company_id=audit.company_id,
            store_id=audit.store_id,
            actor_user_id=actor.id,
            action="audit.stock.count_recorded",
            entity_type="StockAuditItemCount",
            entity_id=count_event.id,
            after_data={"audit_item_id": item.id, "count": counted, "notes": cleaned_notes},
        )
    )
    return count_event


def _store_evidence(file_storage, *, namespace: str) -> str:
    if file_storage is None or not getattr(file_storage, "filename", None):
        raise StockAuditRuleError("Choose an evidence image to attach.")
    original_name = os.path.basename(file_storage.filename.replace("\\", "/"))
    if not original_name or len(original_name) > 255:
        raise StockAuditRuleError("The file name must be 1-255 characters.")
    size = len(file_storage.read() or b"")
    file_storage.stream.seek(0)
    if size <= 0 or size > MAX_EVIDENCE_BYTES:
        raise StockAuditRuleError("Evidence images must be between 1 byte and 5 MB.")
    relative_path = f"{namespace}/{uuid4().hex[:12]}_{original_name}"
    destination = os.path.join(current_app.config["UPLOADS_DIR"], relative_path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    file_storage.save(destination)
    return relative_path


def add_count_evidence(actor: User, *, audit_id: str, item_id: str, count_event_id: str, company_id: str | None = None, file_storage=None) -> StockAuditImage:
    audit = _audit_for_actor(actor, audit_id, company_id=company_id)
    if audit.status != "in_progress":
        raise StockAuditRuleError(f"A {audit.status} audit cannot accept evidence.", 409, "invalid_status")
    _conductor_check(actor, audit)
    count_event = db.session.execute(
        select(StockAuditItemCount).where(
            StockAuditItemCount.id == count_event_id,
            StockAuditItemCount.tenant_container_id == audit.tenant_container_id,
            StockAuditItemCount.company_id == audit.company_id,
        ).join(
            StockAuditItem,
            StockAuditItem.id == StockAuditItemCount.audit_item_id,
        ).where(StockAuditItem.audit_id == audit.id, StockAuditItem.id == item_id)
    ).scalar_one_or_none()
    if count_event is None:
        raise StockAuditRuleError("Count event not found.", 404, "not_found")
    relative_path = _store_evidence(file_storage, namespace=f"stock-audits/{audit.id}")
    image = StockAuditImage(
        tenant_container_id=audit.tenant_container_id,
        company_id=audit.company_id,
        count_event_id=count_event.id,
        image_path=relative_path,
    )
    db.session.add(image)
    db.session.flush()
    return image


def complete_stock_audit(actor: User, *, audit_id: str, company_id: str | None = None, final_counts: dict[str, int] | None = None) -> StockAudit:
    """Finalize the audit and post every variance as a stock adjustment."""
    audit = _audit_for_actor(actor, audit_id, company_id=company_id, lock=True)
    _require_manage_audits(actor, tenant_container_id=audit.tenant_container_id, company_id=audit.company_id, action="edit")
    if audit.status != "in_progress":
        raise StockAuditRuleError(f"A {audit.status} audit cannot be completed.", 409, "invalid_status")
    if not can_access_store(actor, audit.store_id, company_id=audit.company_id, tenant_container_id=audit.tenant_container_id):
        raise StockAuditRuleError("You do not have access to the audited store.", 403, "store_forbidden")
    items = list(
        db.session.execute(
            select(StockAuditItem).where(
                StockAuditItem.tenant_container_id == audit.tenant_container_id,
                StockAuditItem.company_id == audit.company_id,
                StockAuditItem.audit_id == audit.id,
            )
        )
        .scalars()
    )
    before = audit_dict(audit)
    posted: list[dict] = []
    for item in items:
        final_qty = None
        if final_counts and str(item.id) in final_counts:
            try:
                final_qty = int(final_counts[str(item.id)])
            except (TypeError, ValueError):
                raise StockAuditRuleError("Final counts must be whole numbers.") from None
            if final_qty < 0:
                raise StockAuditRuleError("Final counts cannot be negative.")
        else:
            latest = db.session.execute(
                select(StockAuditItemCount.count).where(
                    StockAuditItemCount.tenant_container_id == audit.tenant_container_id,
                    StockAuditItemCount.audit_item_id == item.id,
                ).order_by(StockAuditItemCount.created_at.desc())
            ).scalar_one_or_none()
            if latest is None:
                raise StockAuditRuleError(f"Record a count for {item.product_name} before completing the audit.", 409, "missing_count")
            final_qty = int(latest)
        item.final_audited_qty = final_qty
        db.session.flush()
        delta = final_qty - item.current_stock
        if delta != 0:
            try:
                adjust_inventory(
                    actor,
                    item.product_id,
                    store_id=audit.store_id,
                    quantity_delta=delta,
                    reason=f"stock_audit:{audit.audit_number}",
                    tenant_container_id=audit.tenant_container_id,
                )
            except CatalogRuleError as error:
                raise StockAuditRuleError(str(error), getattr(error, "status_code", 400), getattr(error, "code", "invalid_request")) from None
            posted.append({"product_id": item.product_id, "delta": delta})
    audit.status = "completed"
    audit.completed_at = datetime.now(timezone.utc)
    audit.updated_by_id = actor.id
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=audit.tenant_container_id,
            company_id=audit.company_id,
            store_id=audit.store_id,
            actor_user_id=actor.id,
            action="audit.stock.completed",
            entity_type="StockAudit",
            entity_id=audit.id,
            reason=f"{len(posted)} variance adjustment(s) posted.",
            before_data=before,
            after_data=audit_dict(audit),
        )
    )
    return audit


def cancel_stock_audit(actor: User, *, audit_id: str, company_id: str | None = None, reason: str | None = None) -> StockAudit:
    audit = _audit_for_actor(actor, audit_id, company_id=company_id, lock=True)
    _require_manage_audits(actor, tenant_container_id=audit.tenant_container_id, company_id=audit.company_id, action="edit")
    if audit.status not in {"draft", "in_progress"}:
        raise StockAuditRuleError(f"A {audit.status} audit cannot be cancelled.", 409, "invalid_status")
    before = audit_dict(audit, include_items=False)
    audit.status = "cancelled"
    audit.updated_by_id = actor.id
    db.session.flush()
    db.session.add(
        AuditEvent(
            tenant_container_id=audit.tenant_container_id,
            company_id=audit.company_id,
            store_id=audit.store_id,
            actor_user_id=actor.id,
            action="audit.stock.cancelled",
            entity_type="StockAudit",
            entity_id=audit.id,
            reason=(str(reason or "").strip()[:500]) or None,
            before_data=before,
            after_data=audit_dict(audit, include_items=False),
        )
    )
    return audit


def audit_counts(actor: User, *, audit_id: str, item_id: str, company_id: str | None = None) -> list[dict]:
    audit = _audit_for_actor(actor, audit_id, company_id=company_id)
    _require_manage_audits(actor, tenant_container_id=audit.tenant_container_id, company_id=audit.company_id, action="view")
    rows = db.session.execute(
        select(StockAuditItemCount).where(
            StockAuditItemCount.tenant_container_id == audit.tenant_container_id,
            StockAuditItemCount.company_id == audit.company_id,
            StockAuditItemCount.audit_item_id == item_id,
        ).order_by(StockAuditItemCount.created_at.desc())
    ).scalars()
    return [
        {
            "id": row.id,
            "count": row.count,
            "notes": row.notes,
            "counted_by_id": row.counted_by_id,
            "created_at": row.created_at.isoformat().replace("+00:00", "Z") if row.created_at else None,
        }
        for row in rows
    ]


def audit_evidence(actor: User, *, audit_id: str, count_event_id: str, company_id: str | None = None) -> list[dict]:
    audit = _audit_for_actor(actor, audit_id, company_id=company_id)
    _require_manage_audits(actor, tenant_container_id=audit.tenant_container_id, company_id=audit.company_id, action="view")
    rows = db.session.execute(
        select(StockAuditImage).where(
            StockAuditImage.tenant_container_id == audit.tenant_container_id,
            StockAuditImage.company_id == audit.company_id,
            StockAuditImage.count_event_id == count_event_id,
        ).order_by(StockAuditImage.created_at.asc())
    ).scalars()
    return [
        {
            "id": row.id,
            "image_path": row.image_path,
            "created_at": row.created_at.isoformat().replace("+00:00", "Z") if row.created_at else None,
        }
        for row in rows
    ]
