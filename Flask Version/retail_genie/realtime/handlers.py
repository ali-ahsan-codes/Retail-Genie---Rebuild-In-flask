"""Authenticated Socket.IO handlers; clients never choose or join raw rooms."""

from flask import request
from flask_login import current_user
from sqlalchemy import func, select

from ..auth.store_scope import can_access_store
from ..auth.tenant_context import current_tenant_container_id
from ..auth.tenant_policy import can_access_data_domain
from ..extensions import db, socketio
from ..models import RealtimeEvent, Store
from .service import add_subscription, connection_is_active, register_connection, remove_subscription

NAMESPACE = "/retail"


@socketio.on("connect", namespace=NAMESPACE)
def connect_retail(_auth=None):
    if not current_user.is_authenticated:
        return False
    tenant_id = current_tenant_container_id(current_user)
    if tenant_id is None:
        return False
    register_connection(sid=request.sid, user=current_user, tenant_container_id=tenant_id)
    return True


@socketio.on("subscribe_store", namespace=NAMESPACE)
def subscribe_store(payload=None):
    if not current_user.is_authenticated or not isinstance(payload, dict):
        return {"ok": False, "error": "authentication_required"}
    if not connection_is_active(sid=request.sid, user=current_user):
        return {"ok": False, "error": "authentication_required"}
    store_id = payload.get("store_id")
    tenant_id = current_tenant_container_id(current_user)
    if not isinstance(store_id, str) or not tenant_id:
        return {"ok": False, "error": "invalid_scope"}
    store = db.session.execute(
        select(Store).where(
            Store.id == store_id,
            Store.tenant_container_id == tenant_id,
            Store.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if store is None:
        return {"ok": False, "error": "not_found"}
    if not can_access_store(
        current_user,
        store.id,
        company_id=store.company_id,
        tenant_container_id=tenant_id,
    ):
        return {"ok": False, "error": "store_forbidden"}
    may_subscribe_to_domain = any(
        can_access_data_domain(
            current_user,
            tenant_container_id=tenant_id,
            domain=domain,
            action="view",
            company_id=store.company_id,
            store_id=store.id,
        )
        for domain in ("inventory", "sales")
    )
    if not may_subscribe_to_domain:
        return {"ok": False, "error": "permission_denied"}

    if not add_subscription(
        sid=request.sid,
        user=current_user,
        tenant_container_id=tenant_id,
        store_id=store.id,
        company_id=store.company_id,
    ):
        return {"ok": False, "error": "authentication_required"}
    latest_cursor = db.session.execute(
        select(func.max(RealtimeEvent.id)).where(
            RealtimeEvent.tenant_container_id == tenant_id,
            RealtimeEvent.store_id == store.id,
        )
    ).scalar_one()
    return {"ok": True, "store_id": store.id, "cursor": int(latest_cursor or 0)}


@socketio.on("unsubscribe_store", namespace=NAMESPACE)
def unsubscribe_store(payload=None):
    if not current_user.is_authenticated or not isinstance(payload, dict):
        return {"ok": False, "error": "authentication_required"}
    store_id = payload.get("store_id")
    if not isinstance(store_id, str):
        return {"ok": False, "error": "invalid_scope"}
    remove_subscription(sid=request.sid, store_id=store_id)
    return {"ok": True, "store_id": store_id}


@socketio.on("disconnect", namespace=NAMESPACE)
def disconnect_retail(_reason=None):
    remove_subscription(sid=request.sid)
