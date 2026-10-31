"""Resolve tenant context from signed sessions and active container memberships."""

from __future__ import annotations

from flask import has_request_context, session
from sqlalchemy import or_, select

from ..extensions import db
from ..models import Company, ContainerMembership, TenantContainer


def available_memberships(user_id: str) -> list[ContainerMembership]:
    """Return only active memberships in active containers/companies."""
    statement = (
        select(ContainerMembership)
        .join(TenantContainer, TenantContainer.id == ContainerMembership.tenant_container_id)
        .outerjoin(
            Company,
            (Company.id == ContainerMembership.company_id)
            & (Company.tenant_container_id == ContainerMembership.tenant_container_id),
        )
        .where(
            ContainerMembership.user_id == user_id,
            ContainerMembership.is_active.is_(True),
            TenantContainer.is_active.is_(True),
            or_(ContainerMembership.company_id.is_(None), Company.is_active.is_(True)),
        )
        .order_by(ContainerMembership.tenant_container_id.asc())
    )
    return list(db.session.execute(statement).scalars())


def current_membership(user, *, tenant_container_id: str | None = None) -> ContainerMembership | None:
    """Resolve the active membership; never infer tenant scope from company_id."""
    if user is None or not getattr(user, "is_authenticated", False) or getattr(user, "role", None) == "super_admin":
        return None

    selected_id = tenant_container_id
    if selected_id is None and has_request_context():
        selected_id = session.get("active_container_id")
    if selected_id is None:
        candidates = available_memberships(user.id)
        if len(candidates) != 1:
            return None
        return candidates[0]

    statement = (
        select(ContainerMembership)
        .join(TenantContainer, TenantContainer.id == ContainerMembership.tenant_container_id)
        .outerjoin(
            Company,
            (Company.id == ContainerMembership.company_id)
            & (Company.tenant_container_id == ContainerMembership.tenant_container_id),
        )
        .where(
            ContainerMembership.user_id == user.id,
            ContainerMembership.tenant_container_id == selected_id,
            ContainerMembership.is_active.is_(True),
            TenantContainer.is_active.is_(True),
            or_(ContainerMembership.company_id.is_(None), Company.is_active.is_(True)),
        )
    )
    return db.session.execute(statement).scalar_one_or_none()


def current_tenant_container_id(user=None) -> str | None:
    """Return the one active container selected for this request/account."""
    if user is None:
        try:
            from flask_login import current_user

            user = current_user
        except RuntimeError:
            return None
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "role", None) == "super_admin":
        if not has_request_context():
            return None
        selected_id = session.get("active_container_id")
        if not selected_id:
            return None
        container = db.session.get(TenantContainer, selected_id)
        return selected_id if container is not None and container.is_active else None
    membership = current_membership(user)
    return membership.tenant_container_id if membership else None


def has_tenant_membership(user, tenant_container_id: str) -> bool:
    """Check one requested tenant without granting access to sibling containers."""
    if user is None or not getattr(user, "is_authenticated", False) or not tenant_container_id:
        return False
    if getattr(user, "role", None) == "super_admin":
        container = db.session.get(TenantContainer, tenant_container_id)
        return bool(container and container.is_active)
    membership = current_membership(user, tenant_container_id=tenant_container_id)
    return membership is not None


def select_container_for_session(user, tenant_container_id: str) -> bool:
    """Set an active container only when an active membership proves access."""
    if not has_request_context() or user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "role", None) == "super_admin":
        container = db.session.get(TenantContainer, tenant_container_id)
        if container is None or not container.is_active:
            return False
    elif current_membership(user, tenant_container_id=tenant_container_id) is None:
        return False
    session["active_container_id"] = tenant_container_id
    session.pop("pending_tenant_selection", None)
    from ..realtime.service import clear_user_subscriptions

    clear_user_subscriptions(user.id)
    return True
