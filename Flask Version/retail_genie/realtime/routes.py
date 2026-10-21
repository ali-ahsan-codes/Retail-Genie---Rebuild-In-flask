"""Authenticated cursor-based replay for events missed while disconnected."""

from flask import jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func, select

from ..auth.store_scope import can_access_store
from ..auth.tenant_context import current_tenant_container_id
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db
from ..models import RealtimeEvent, Store
from . import realtime_bp
from .service import event_message


def _private_json(**payload):
    response = jsonify(**payload)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@realtime_bp.get("/api/v1/realtime/stores")
@login_required
def realtime_stores():
    tenant_id = current_tenant_container_id(current_user)
    if not tenant_id:
        return _private_json(stores=[])
    stores = db.session.execute(
        select(Store).where(
            Store.tenant_container_id == tenant_id,
            Store.is_active.is_(True),
        ).order_by(Store.id.asc()).limit(501)
    ).scalars().all()
    visible = []
    for store in stores:
        if len(visible) >= 500:
            break
        if not can_access_store(
            current_user,
            store.id,
            company_id=store.company_id,
            tenant_container_id=tenant_id,
        ):
            continue
        if any(
            can_access_data_domain(
                current_user,
                tenant_container_id=tenant_id,
                domain=domain,
                action="view",
                company_id=store.company_id,
                store_id=store.id,
            )
            for domain in ("inventory", "sales")
        ):
            visible.append(store.id)
    return _private_json(stores=visible)


@realtime_bp.get("/api/v1/realtime/events")
@login_required
def replay_events():
    tenant_id = current_tenant_container_id(current_user)
    store_id = request.args.get("store_id", "")
    raw_cursor = request.args.get("after_id", "0")
    if not raw_cursor.isdigit():
        return _private_json(error="invalid_cursor", message="after_id must be a nonnegative event ID."), 400
    after_id = int(raw_cursor)
    if after_id > 9223372036854775807:
        return _private_json(error="invalid_cursor", message="after_id exceeds the supported cursor range."), 400

    store = db.session.execute(
        select(Store).where(
            Store.id == store_id,
            Store.tenant_container_id == tenant_id,
            Store.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if store is None:
        return _private_json(error="not_found"), 404
    if not can_access_store(
        current_user,
        store.id,
        company_id=store.company_id,
        tenant_container_id=tenant_id,
    ):
        return _private_json(error="store_forbidden"), 403
    visible_domains = [
        domain
        for domain in ("inventory", "sales")
        if can_access_data_domain(
            current_user,
            tenant_container_id=tenant_id,
            domain=domain,
            action="view",
            company_id=store.company_id,
            store_id=store.id,
        )
    ]
    if not visible_domains:
        return _private_json(error="permission_denied"), 403

    cursor_floor = db.session.execute(
        select(func.max(RealtimeEvent.cursor_floor)).where(
            RealtimeEvent.tenant_container_id == tenant_id,
            RealtimeEvent.company_id == store.company_id,
            RealtimeEvent.store_id == store.id,
            RealtimeEvent.domain.in_(visible_domains),
        )
    ).scalar_one()
    if cursor_floor is not None and after_id < int(cursor_floor):
        return _private_json(
            error="cursor_expired",
            message="This replay cursor predates retained events; refresh the page for a current snapshot.",
            minimum_cursor=int(cursor_floor),
        ), 410

    fetched = list(
        db.session.execute(
            select(RealtimeEvent)
            .where(
                RealtimeEvent.tenant_container_id == tenant_id,
                RealtimeEvent.company_id == store.company_id,
                RealtimeEvent.store_id == store.id,
                RealtimeEvent.id > after_id,
            )
            .order_by(RealtimeEvent.id.asc())
            .limit(101)
        ).scalars()
    )
    has_more = len(fetched) > 100
    scanned = fetched[:100]
    visible = []
    for event in scanned:
        if event.recipient_user_id and event.recipient_user_id != current_user.id:
            continue
        if event.domain == "access":
            continue
        if not can_access_data_domain(
            current_user,
            tenant_container_id=tenant_id,
            domain=event.domain,
            action="view",
            company_id=event.company_id,
            store_id=event.store_id,
        ):
            continue
        if event.product_owner_company_id and event.product_id:
            owner_store_id = store.id if event.product_owner_company_id == store.company_id else None
            if not can_access_data_domain(
                current_user,
                tenant_container_id=tenant_id,
                domain="product_catalog",
                action="view",
                company_id=event.product_owner_company_id,
                store_id=owner_store_id,
            ):
                continue
        visible.append(event_message(event))
    next_cursor = scanned[-1].id if scanned else after_id
    return _private_json(events=visible, next_cursor=next_cursor, has_more=has_more)
