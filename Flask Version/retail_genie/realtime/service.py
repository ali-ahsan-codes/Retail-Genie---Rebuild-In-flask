"""Realtime subscription registry, reauthorization, and best-effort delivery."""

from __future__ import annotations

from threading import RLock

from flask import current_app
from sqlalchemy import or_, select

from ..extensions import db, socketio
from ..models import (
    ContainerMembership,
    Company,
    RealtimeEvent,
    Store,
    TenantContainer,
    TenantDataPolicy,
    TenantDataPolicyScope,
    User,
    UserStoreAssignment,
    ROLE_PERMISSION_LIMITS,
)

_DOMAIN_LEGACY_PERMISSION = {
    "product_catalog": "manage_products",
    "inventory": "manage_products",
}


def initialize_realtime_registry(app) -> None:
    """Create a process-local connection/subscription registry for the single-host MVP."""
    app.extensions["retail_genie_realtime_subscriptions"] = {
        "connections": {},
        "entries": {},
        "lock": RLock(),
    }


def register_connection(*, sid: str, user: User, tenant_container_id: str) -> None:
    registry = _registry()
    with registry["lock"]:
        registry["connections"][sid] = {
            "user_id": user.id,
            "auth_version": user.auth_version,
            "tenant_container_id": tenant_container_id,
        }


def connection_is_active(*, sid: str, user: User) -> bool:
    registry = _registry()
    with registry["lock"]:
        connection = registry["connections"].get(sid)
        return bool(
            connection
            and connection["user_id"] == user.id
            and str(connection["auth_version"]) == str(user.auth_version)
        )


def _registry():
    return current_app.extensions["retail_genie_realtime_subscriptions"]


def add_subscription(*, sid: str, user: User, tenant_container_id: str, store_id: str) -> bool:
    registry = _registry()
    with registry["lock"]:
        connection = registry["connections"].get(sid)
        if (
            connection is None
            or connection["user_id"] != user.id
            or str(connection["auth_version"]) != str(user.auth_version)
            or connection["tenant_container_id"] != tenant_container_id
        ):
            return False
        registry["entries"][(sid, store_id)] = {
            "sid": sid,
            "user_id": user.id,
            "auth_version": user.auth_version,
            "tenant_container_id": tenant_container_id,
            "store_id": store_id,
        }
        return True


def remove_subscription(*, sid: str, store_id: str | None = None) -> None:
    registry = _registry()
    with registry["lock"]:
        for key, value in list(registry["entries"].items()):
            if value["sid"] == sid and (store_id is None or value["store_id"] == store_id):
                registry["entries"].pop(key, None)
        if store_id is None:
            registry["connections"].pop(sid, None)


def clear_user_subscriptions(user_id: str) -> None:
    """Revoke a user's process-local sockets on logout or tenant switch."""
    if not user_id:
        return
    try:
        registry = _registry()
    except (RuntimeError, KeyError):
        return
    with registry["lock"]:
        sids = [
            sid
            for sid, connection in registry["connections"].items()
            if connection["user_id"] == user_id
        ]
        for sid in sids:
            registry["connections"].pop(sid, None)
        for key, value in list(registry["entries"].items()):
            if value["user_id"] == user_id:
                registry["entries"].pop(key, None)
    for sid in sids:
        try:
            socketio.server.disconnect(sid, namespace="/retail")
        except Exception as error:
            # The connection is already unauthorized in the registry even if
            # the transport closed between the lookup and explicit disconnect.
            current_app.logger.debug("Realtime socket revoke skipped (%s)", type(error).__name__)


def _policy_allows(
    *,
    user: User,
    membership: ContainerMembership | None,
    tenant_container_id: str,
    domain: str,
    company_id: str,
    store_id: str | None,
    is_platform_admin: bool,
) -> bool:
    policy = db.session.execute(
        select(TenantDataPolicy).where(
            TenantDataPolicy.tenant_container_id == tenant_container_id,
            TenantDataPolicy.domain == domain,
        )
    ).scalar_one_or_none()
    if policy is None or not policy.is_enabled or policy.sharing_mode == "disabled":
        return False
    if is_platform_admin or policy.sharing_mode == "container":
        return True
    if membership is None:
        return False
    if policy.sharing_mode == "company":
        return membership.company_id == company_id
    if policy.sharing_mode == "assigned_store":
        if store_id is None or membership.company_id != company_id:
            return False
        return db.session.execute(
            select(UserStoreAssignment.id).where(
                UserStoreAssignment.tenant_container_id == tenant_container_id,
                UserStoreAssignment.user_id == user.id,
                UserStoreAssignment.company_id == company_id,
                UserStoreAssignment.store_id == store_id,
                UserStoreAssignment.is_active.is_(True),
            )
        ).scalar_one_or_none() is not None
    if policy.sharing_mode == "selected_units":
        if store_id is None and company_id is None:
            return False
        scopes = db.session.execute(
            select(TenantDataPolicyScope.is_allowed).where(
                TenantDataPolicyScope.tenant_container_id == tenant_container_id,
                TenantDataPolicyScope.policy_id == policy.id,
                or_(
                    TenantDataPolicyScope.company_id == company_id,
                    TenantDataPolicyScope.store_id == store_id if store_id else False,
                ),
            )
        ).scalars().all()
        return bool(scopes) and all(scopes)
    return False


def _has_domain_view(user: User, membership: ContainerMembership | None, domain: str) -> bool:
    role = membership.role if membership is not None else user.role
    if role in {"super_admin", "company_admin", "admin"}:
        return True
    permissions = set(membership.permissions if membership is not None else user.permissions or [])
    permissions.intersection_update(ROLE_PERMISSION_LIMITS.get(role, frozenset()))
    return bool({f"{domain}.view", _DOMAIN_LEGACY_PERMISSION[domain]}.intersection(permissions))


def can_user_receive_inventory_event(
    *,
    user_id: str,
    auth_version: int,
    event: RealtimeEvent,
) -> bool:
    """Recheck current user, store, role, and both relevant domain policies.

    This check deliberately does not read the publishing HTTP request's active
    tenant session; it authorizes the socket subscriber's stored tenant against
    their current membership/permissions in the database.
    """
    user = db.session.get(User, user_id)
    if user is None or not user.is_active or str(user.auth_version) != str(auth_version):
        return False
    tenant = db.session.get(TenantContainer, event.tenant_container_id)
    if tenant is None or not tenant.is_active:
        return False
    store = db.session.execute(
        select(Store).where(
            Store.id == event.store_id,
            Store.tenant_container_id == event.tenant_container_id,
            Store.company_id == event.company_id,
            Store.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if store is None:
        return False
    product_company = db.session.execute(
        select(Company).where(
            Company.id == event.product_owner_company_id,
            Company.tenant_container_id == event.tenant_container_id,
            Company.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if product_company is None:
        return False

    is_platform_admin = user.role == "super_admin"
    membership = None
    if not is_platform_admin:
        membership = db.session.execute(
            select(ContainerMembership).where(
                ContainerMembership.user_id == user.id,
                ContainerMembership.tenant_container_id == event.tenant_container_id,
                ContainerMembership.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if membership is None or membership.company_id != store.company_id:
            return False
        role = membership.role
        if role not in {"company_admin", "admin"}:
            assignment = db.session.execute(
                select(UserStoreAssignment.id).where(
                    UserStoreAssignment.tenant_container_id == event.tenant_container_id,
                    UserStoreAssignment.company_id == store.company_id,
                    UserStoreAssignment.user_id == user.id,
                    UserStoreAssignment.store_id == store.id,
                    UserStoreAssignment.is_active.is_(True),
                )
            ).scalar_one_or_none()
            if assignment is None:
                return False

    if not _has_domain_view(user, membership, "inventory") or not _has_domain_view(user, membership, "product_catalog"):
        return False
    if not _policy_allows(
        user=user,
        membership=membership,
        tenant_container_id=event.tenant_container_id,
        domain="inventory",
        company_id=store.company_id,
        store_id=store.id,
        is_platform_admin=is_platform_admin,
    ):
        return False
    product_store_id = store.id if product_company.id == store.company_id else None
    return _policy_allows(
        user=user,
        membership=membership,
        tenant_container_id=event.tenant_container_id,
        domain="product_catalog",
        company_id=product_company.id,
        store_id=product_store_id,
        is_platform_admin=is_platform_admin,
    )


def event_message(event: RealtimeEvent) -> dict:
    return {
        "id": event.id,
        "type": event.event_type,
        "tenant_container_id": event.tenant_container_id,
        "company_id": event.company_id,
        "store_id": event.store_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "data": dict(event.payload or {}),
    }


def publish_realtime_event(event_id: int) -> None:
    """Deliver only to currently authorized sockets; replay API covers missed push."""
    try:
        event = db.session.get(RealtimeEvent, event_id)
        if event is None:
            return
        registry = _registry()
        with registry["lock"]:
            subscribers = [
                (key, dict(value))
                for key, value in registry["entries"].items()
                if value["tenant_container_id"] == event.tenant_container_id
                and value["store_id"] == event.store_id
            ]
        for key, subscriber in subscribers:
            if not can_user_receive_inventory_event(
                user_id=subscriber["user_id"],
                auth_version=subscriber["auth_version"],
                event=event,
            ):
                with registry["lock"]:
                    registry["entries"].pop(key, None)
                continue
            socketio.emit(
                event.event_type,
                event_message(event),
                to=subscriber["sid"],
                namespace="/retail",
            )
    except Exception as error:  # The committed event remains available to replay.
        current_app.logger.warning("Realtime publish deferred (%s)", type(error).__name__)
