"""Realtime subscription registry, reauthorization, and best-effort delivery."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import monotonic

from flask import current_app
from sqlalchemy import delete, func, or_, select

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
        "dispatch_lock": RLock(),
        "dispatching": set(),
        "published_ids": set(),
        "published_order": deque(maxlen=8192),
        "cursor": 0,
        "startup_cursor": 0,
        "dispatcher_started": False,
        "last_prune_at": 0.0,
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


def add_subscription(*, sid: str, user: User, tenant_container_id: str, store_id: str, company_id: str | None = None) -> bool:
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
            "company_id": company_id,
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
    required = {f"{domain}.view"}
    legacy_permission = _DOMAIN_LEGACY_PERMISSION.get(domain)
    if legacy_permission:
        required.add(legacy_permission)
    return bool(required.intersection(permissions))


def can_user_receive_realtime_event(
    *,
    user_id: str,
    auth_version: int,
    event: RealtimeEvent,
) -> bool:
    """Reauthorize a socket against current membership, role, store and domain policy."""
    user = db.session.get(User, user_id)
    if user is None:
        return False
    tenant = db.session.get(TenantContainer, event.tenant_container_id)
    if tenant is None or not tenant.is_active:
        return False

    # Revocation notices are deliberately minimal and recipient-only. They must
    # still reach the affected socket after its auth version or assignment changed.
    if event.domain == "access":
        return event.recipient_user_id == user.id
    if not user.is_active or str(user.auth_version) != str(auth_version):
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
        if membership is None:
            return False

    store = None
    if event.store_id:
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
        if membership is not None and membership.company_id != store.company_id:
            return False
        if membership is not None and membership.role not in {"company_admin", "admin"}:
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

    if event.company_id and membership is not None and membership.company_id != event.company_id:
        return False
    if not _has_domain_view(user, membership, event.domain):
        return False
    if event.company_id and not _policy_allows(
        user=user,
        membership=membership,
        tenant_container_id=event.tenant_container_id,
        domain=event.domain,
        company_id=event.company_id,
        store_id=event.store_id,
        is_platform_admin=is_platform_admin,
    ):
        return False

    if event.product_owner_company_id and event.product_id:
        product_company = db.session.execute(
            select(Company).where(
                Company.id == event.product_owner_company_id,
                Company.tenant_container_id == event.tenant_container_id,
                Company.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if product_company is None or not _has_domain_view(user, membership, "product_catalog"):
            return False
        product_store_id = store.id if store is not None and product_company.id == store.company_id else None
        return _policy_allows(
            user=user,
            membership=membership,
            tenant_container_id=event.tenant_container_id,
            domain="product_catalog",
            company_id=product_company.id,
            store_id=product_store_id,
            is_platform_admin=is_platform_admin,
        )
    return True


def can_user_receive_inventory_event(*, user_id: str, auth_version: int, event: RealtimeEvent) -> bool:
    """Backward-compatible alias used by older callers and tests."""
    return can_user_receive_realtime_event(user_id=user_id, auth_version=auth_version, event=event)


def event_message(event: RealtimeEvent) -> dict:
    return {
        "id": event.id,
        "type": event.event_type,
        "domain": event.domain,
        "tenant_container_id": event.tenant_container_id,
        "company_id": event.company_id,
        "store_id": event.store_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "data": {} if event.domain == "access" else dict(event.payload or {}),
    }


def stage_access_revocation(
    *,
    user_id: str,
    tenant_container_id: str,
    company_id: str | None = None,
    store_id: str | None = None,
    actor_user_id: str | None = None,
) -> int:
    """Write an access-change outbox row in the same transaction as ACL edits."""
    event = RealtimeEvent(
        tenant_container_id=tenant_container_id,
        company_id=company_id,
        store_id=store_id,
        domain="access",
        event_type="access.revoked",
        payload={},
        recipient_user_id=user_id,
        actor_user_id=actor_user_id,
    )
    db.session.add(event)
    db.session.flush()
    return event.id


def stage_container_access_revocations(*, tenant_container_id: str, actor_user_id: str | None = None) -> list[int]:
    """Stage per-user invalidations after a tenant-wide policy change."""
    memberships = db.session.execute(
        select(ContainerMembership).where(
            ContainerMembership.tenant_container_id == tenant_container_id,
            ContainerMembership.is_active.is_(True),
        )
    ).scalars().all()
    return [
        stage_access_revocation(
            user_id=membership.user_id,
            tenant_container_id=tenant_container_id,
            company_id=membership.company_id,
            actor_user_id=actor_user_id,
        )
        for membership in memberships
    ]


def stage_company_access_revocations(
    *, tenant_container_id: str, company_id: str, actor_user_id: str | None = None
) -> list[int]:
    memberships = db.session.execute(
        select(ContainerMembership).where(
            ContainerMembership.tenant_container_id == tenant_container_id,
            ContainerMembership.company_id == company_id,
            ContainerMembership.is_active.is_(True),
        )
    ).scalars().all()
    return [
        stage_access_revocation(
            user_id=membership.user_id,
            tenant_container_id=tenant_container_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
        )
        for membership in memberships
    ]


def stage_user_access_revocations(
    *, user_id: str, actor_user_id: str | None = None, include_inactive: bool = False
) -> list[int]:
    statement = select(ContainerMembership).where(ContainerMembership.user_id == user_id)
    if not include_inactive:
        statement = statement.where(ContainerMembership.is_active.is_(True))
    memberships = db.session.execute(statement).scalars().all()
    return [
        stage_access_revocation(
            user_id=user_id,
            tenant_container_id=membership.tenant_container_id,
            company_id=membership.company_id,
            actor_user_id=actor_user_id,
        )
        for membership in memberships
    ]


def _claim_event(registry, event_id: int) -> bool:
    with registry["dispatch_lock"]:
        if event_id in registry["published_ids"] or event_id in registry["dispatching"]:
            return False
        registry["dispatching"].add(event_id)
        return True


def _finish_event(registry, event_id: int, succeeded: bool) -> None:
    with registry["dispatch_lock"]:
        registry["dispatching"].discard(event_id)
        if succeeded:
            if len(registry["published_order"]) == registry["published_order"].maxlen:
                expired = registry["published_order"][0]
                registry["published_ids"].discard(expired)
            registry["published_order"].append(event_id)
            registry["published_ids"].add(event_id)


def _matching_subscribers(registry, event: RealtimeEvent) -> list[tuple[tuple[str, str], dict]]:
    with registry["lock"]:
        entries = list(registry["entries"].items())
    selected = []
    for key, value in entries:
        if value["tenant_container_id"] != event.tenant_container_id:
            continue
        if event.domain == "access":
            if value["user_id"] != event.recipient_user_id:
                continue
            if event.store_id and value["store_id"] != event.store_id:
                continue
            if event.company_id and value.get("company_id") != event.company_id:
                continue
        elif event.store_id:
            if value["store_id"] != event.store_id:
                continue
        elif event.company_id:
            if value.get("company_id") != event.company_id:
                continue
        selected.append((key, dict(value)))
    return selected


def _revoke_subscriber(registry, key: tuple[str, str], subscriber: dict, event: RealtimeEvent) -> None:
    sid, store_id = key
    socketio.emit("access.revoked", event_message(event), to=sid, namespace="/retail")
    remove_subscription(sid=sid, store_id=store_id)
    with registry["lock"]:
        has_other_subscriptions = any(entry["sid"] == sid for entry in registry["entries"].values())
        if not has_other_subscriptions:
            registry["connections"].pop(sid, None)
    if not has_other_subscriptions:
        try:
            socketio.server.disconnect(sid, namespace="/retail")
        except Exception as error:
            current_app.logger.debug("Realtime access revoke disconnect skipped (%s)", type(error).__name__)


def publish_realtime_event(event_id: int) -> bool:
    """Deliver a committed event to local sockets; other workers poll the same outbox."""
    event = db.session.get(RealtimeEvent, event_id)
    if event is None:
        return True
    registry = _registry()
    if not _claim_event(registry, event.id):
        return True
    succeeded = False
    try:
        subscribers = _matching_subscribers(registry, event)
        for key, subscriber in subscribers:
            if event.domain == "access":
                _revoke_subscriber(registry, key, subscriber, event)
                continue
            if not can_user_receive_realtime_event(
                user_id=subscriber["user_id"],
                auth_version=subscriber["auth_version"],
                event=event,
            ):
                remove_subscription(sid=subscriber["sid"], store_id=subscriber["store_id"])
                continue
            socketio.emit(
                event.event_type,
                event_message(event),
                to=subscriber["sid"],
                namespace="/retail",
            )
        succeeded = True
    except Exception as error:
        current_app.logger.warning("Realtime publish deferred (%s)", type(error).__name__)
    finally:
        _finish_event(registry, event.id, succeeded)
    return succeeded


def realtime_dispatch_once(app=None) -> int:
    """Poll and deliver a batch of committed outbox rows (also used by tests)."""
    if app is None:
        app = current_app._get_current_object()
    registry = app.extensions["retail_genie_realtime_subscriptions"]
    published = 0
    with app.app_context():
        cursor = int(registry.get("cursor", 0))
        startup_cursor = int(registry.get("startup_cursor", 0))
        new_ids = db.session.execute(
            select(RealtimeEvent.id)
            .where(RealtimeEvent.id > cursor)
            .order_by(RealtimeEvent.id.asc())
            .limit(500)
        ).scalars().all()
        for event_id in new_ids:
            event_id = int(event_id)
            if not publish_realtime_event(event_id):
                break
            cursor = max(cursor, event_id)
            published += 1
        registry["cursor"] = cursor

        # Auto-increment IDs are allocated before commit. A longer transaction
        # can therefore become visible behind this worker's cursor; repeatedly
        # rescan a bounded recent overlap to catch that late commit.
        overlap_floor = max(startup_cursor, cursor - 500)
        late_ids = db.session.execute(
            select(RealtimeEvent.id)
            .where(RealtimeEvent.id > overlap_floor, RealtimeEvent.id <= cursor)
            .order_by(RealtimeEvent.id.desc())
            .limit(500)
        ).scalars().all()
        for event_id in sorted(int(value) for value in late_ids):
            with registry["dispatch_lock"]:
                already_published = event_id in registry["published_ids"]
            if already_published:
                continue
            if not publish_realtime_event(event_id):
                break
            published += 1
        db.session.remove()
    return published


def prune_realtime_events(*, retention_days: int | None = None) -> int:
    """Delete expired feed rows but keep one cursor anchor for every event scope."""
    days = retention_days or int(current_app.config.get("REALTIME_RETENTION_DAYS", 30))
    if days < 1 or days > 3650:
        raise ValueError("Realtime event retention must be between 1 and 3650 days.")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    expired_rows = db.session.execute(
        select(RealtimeEvent)
        .where(RealtimeEvent.created_at < cutoff)
        .order_by(RealtimeEvent.id.asc())
    ).scalars().all()
    groups: dict[tuple, list[RealtimeEvent]] = {}
    for event in expired_rows:
        scope = (
            event.tenant_container_id,
            event.company_id,
            event.store_id,
            event.domain,
            event.recipient_user_id,
        )
        groups.setdefault(scope, []).append(event)

    deleted_ids: list[int] = []
    for events in groups.values():
        anchor = events[-1]
        deleted = events[:-1]
        if not deleted:
            continue
        inherited_floor = max((event.cursor_floor or 0 for event in events), default=0)
        anchor.cursor_floor = max(inherited_floor, max(event.id for event in deleted))
        deleted_ids.extend(event.id for event in deleted)
    if deleted_ids:
        db.session.execute(delete(RealtimeEvent).where(RealtimeEvent.id.in_(deleted_ids)))
    db.session.commit()
    return len(deleted_ids)


def start_realtime_dispatcher(app) -> None:
    """Start one database-polling publisher per web process for multi-worker fan-out."""
    if app.testing or not app.config.get("REALTIME_DISPATCH_ENABLED", True):
        return
    registry = app.extensions["retail_genie_realtime_subscriptions"]
    with registry["lock"]:
        if registry["dispatcher_started"]:
            return
        registry["dispatcher_started"] = True
    with app.app_context():
        initial_cursor = int(db.session.execute(select(func.coalesce(func.max(RealtimeEvent.id), 0))).scalar_one())
        registry["cursor"] = initial_cursor
        registry["startup_cursor"] = initial_cursor
    socketio.start_background_task(_realtime_dispatch_loop, app)


def _realtime_dispatch_loop(app) -> None:
    while True:
        try:
            realtime_dispatch_once(app)
            registry = app.extensions["retail_genie_realtime_subscriptions"]
            now = monotonic()
            sweep_seconds = max(60, int(app.config.get("REALTIME_RETENTION_SWEEP_SECONDS", 21600)))
            if now - registry["last_prune_at"] >= sweep_seconds:
                with app.app_context():
                    prune_realtime_events()
                registry["last_prune_at"] = now
        except Exception as error:
            app.logger.warning("Realtime outbox poll deferred (%s)", type(error).__name__)
        socketio.sleep(max(0.1, float(app.config.get("REALTIME_POLL_INTERVAL_SECONDS", 0.5))))
