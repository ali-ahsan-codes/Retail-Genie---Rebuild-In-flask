"""Data-domain sharing decisions within a tenant container.

Tenant boundaries are unconditional. Policies may narrow or extend access only
inside the selected container; they never authorize another container.
"""

from __future__ import annotations

from sqlalchemy import or_, select

from ..extensions import db
from ..models import (
    DATA_DOMAINS,
    ROLE_PERMISSION_LIMITS,
    Company,
    ContainerMembership,
    Store,
    TenantContainer,
    TenantDataPolicy,
    TenantDataPolicyScope,
    UserStoreAssignment,
)
from .tenant_context import current_membership, current_tenant_container_id

_DOMAIN_PERMISSION = {
    "product_catalog": "manage_products",
    "inventory": "manage_products",
    "customers": "manage_orders",
    "open_bills": None,
    "sales": None,
    "staff_accounts": "manage_users",
    "suppliers": "manage_suppliers",
    "reports": "view_reports",
    "files": "manage_cloud_files",
    "audit": "view_activity_logs",
    "cashups": "manage_settings",
    "settings": "manage_settings",
}


def _actor_permissions(user, membership: ContainerMembership | None) -> tuple[str, set[str]]:
    role = membership.role if membership is not None else user.role
    raw_permissions = membership.permissions if membership is not None else user.permissions
    permissions = set(raw_permissions or [])
    allowed_by_role = ROLE_PERMISSION_LIMITS.get(role, frozenset())
    return role, permissions.intersection(allowed_by_role)


def can_access_data_domain(
    user,
    *,
    tenant_container_id: str,
    domain: str,
    action: str = "view",
    company_id: str | None = None,
    store_id: str | None = None,
) -> bool:
    """Authorize view/add/edit/delete against membership, role, and policy.

    ``company_id`` and ``store_id`` identify the record's owning unit, not the
    acting user's preferred scope. A missing policy denies access by default.
    Explicit denials in selected-unit mode override grants.
    """
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or domain not in DATA_DOMAINS
        or action not in {"view", "add", "edit", "delete"}
        or not tenant_container_id
    ):
        return False

    container = db.session.get(TenantContainer, tenant_container_id)
    if container is None or not container.is_active:
        return False

    is_platform_admin = getattr(user, "role", None) == "super_admin"
    if is_platform_admin:
        membership = None
    else:
        if current_tenant_container_id(user) != tenant_container_id:
            return False
        membership = current_membership(user, tenant_container_id=tenant_container_id)
        if membership is None:
            return False

    if company_id is not None:
        company = db.session.execute(
            select(Company).where(
                Company.id == company_id,
                Company.tenant_container_id == tenant_container_id,
                Company.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if company is None:
            return False
    if store_id is not None:
        store = db.session.execute(
            select(Store).where(
                Store.id == store_id,
                Store.tenant_container_id == tenant_container_id,
                Store.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if store is None or (company_id is not None and store.company_id != company_id):
            return False

    # A Main Admin can administer the selected tenant, but still cannot use a
    # business-domain policy to cross a container boundary or inactive unit.
    if not is_platform_admin:
        role, permissions = _actor_permissions(user, membership)
        legacy_permission = _DOMAIN_PERMISSION[domain]
        action_permission = f"{domain}.{action}"
        if role not in {"company_admin", "admin"}:
            if action_permission not in permissions and (legacy_permission is None or legacy_permission not in permissions):
                return False

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
    if policy.sharing_mode == "company":
        return company_id is not None and membership.company_id == company_id
    if policy.sharing_mode == "assigned_store":
        if store_id is None:
            return False
        return db.session.execute(
            select(UserStoreAssignment.id).where(
                UserStoreAssignment.tenant_container_id == tenant_container_id,
                UserStoreAssignment.user_id == user.id,
                UserStoreAssignment.store_id == store_id,
                UserStoreAssignment.is_active.is_(True),
            )
        ).scalar_one_or_none() is not None
    if policy.sharing_mode == "selected_units":
        if company_id is None and store_id is None:
            return False
        matching_scopes = db.session.execute(
            select(TenantDataPolicyScope.is_allowed).where(
                TenantDataPolicyScope.tenant_container_id == tenant_container_id,
                TenantDataPolicyScope.policy_id == policy.id,
                or_(
                    (TenantDataPolicyScope.company_id == company_id) if company_id else False,
                    (TenantDataPolicyScope.store_id == store_id) if store_id else False,
                ),
            )
        ).scalars().all()
        return bool(matching_scopes) and all(matching_scopes)
    return False
