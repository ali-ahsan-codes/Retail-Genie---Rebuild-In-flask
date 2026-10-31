"""Server-side tenant/company/store access checks; never trust client scope IDs."""

from sqlalchemy import select

from ..extensions import db
from ..models import Company, Store, TenantContainer, UserStoreAssignment
from .tenant_context import current_membership, current_tenant_container_id
from .tenant_policy import can_access_data_domain


def accessible_store_ids(
    user,
    *,
    company_id: str | None = None,
    tenant_container_id: str | None = None,
) -> set[str]:
    """Return active stores in one authorized container and optional company."""
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    company = db.session.get(Company, company_id) if company_id else None
    if company_id and (company is None or not company.is_active):
        return set()
    container_id = tenant_container_id or (company.tenant_container_id if company is not None else None)
    if container_id is None:
        container_id = current_tenant_container_id(user)
    if container_id is None:
        return set()
    if company is not None and company.tenant_container_id != container_id:
        return set()

    base = select(Store.id).where(
        Store.tenant_container_id == container_id,
        Store.is_active.is_(True),
    )
    if company_id is not None:
        base = base.where(Store.company_id == company_id)

    if getattr(user, "role", None) == "super_admin":
        return set(db.session.execute(base).scalars())

    membership = current_membership(user, tenant_container_id=container_id)
    if membership is None or current_tenant_container_id(user) != container_id:
        return set()
    if company_id is not None and membership.company_id != company_id:
        return set()
    if user.is_company_admin:
        scoped = base
        if membership.company_id is not None:
            scoped = scoped.where(Store.company_id == membership.company_id)
        return set(db.session.execute(scoped).scalars())

    assignments = (
        select(UserStoreAssignment.store_id)
        .join(
            Store,
            (Store.id == UserStoreAssignment.store_id)
            & (Store.tenant_container_id == UserStoreAssignment.tenant_container_id)
            & (Store.company_id == UserStoreAssignment.company_id),
        )
        .where(
            UserStoreAssignment.tenant_container_id == container_id,
            UserStoreAssignment.user_id == user.id,
            UserStoreAssignment.is_active.is_(True),
            Store.is_active.is_(True),
        )
    )
    if company_id is not None:
        assignments = assignments.where(UserStoreAssignment.company_id == company_id)
    return set(db.session.execute(assignments).scalars())


def can_access_store(
    user,
    store_id: str,
    *,
    company_id: str | None = None,
    tenant_container_id: str | None = None,
) -> bool:
    """Require tenant membership plus company-admin scope or an active assignment."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    store = db.session.get(Store, store_id)
    if store is None or not store.is_active:
        return False
    if company_id is not None and store.company_id != company_id:
        return False
    if tenant_container_id is not None and store.tenant_container_id != tenant_container_id:
        return False
    container = db.session.get(TenantContainer, store.tenant_container_id)
    if container is None or not container.is_active:
        return False
    if getattr(user, "role", None) == "super_admin":
        return True

    membership = current_membership(user, tenant_container_id=store.tenant_container_id)
    if membership is None or current_tenant_container_id(user) != store.tenant_container_id:
        return False
    if user.is_company_admin and membership.company_id == store.company_id:
        return True
    return db.session.execute(
        select(UserStoreAssignment.id).where(
            UserStoreAssignment.tenant_container_id == store.tenant_container_id,
            UserStoreAssignment.user_id == user.id,
            UserStoreAssignment.company_id == store.company_id,
            UserStoreAssignment.store_id == store.id,
            UserStoreAssignment.is_active.is_(True),
        )
    ).scalar_one_or_none() is not None


def can_view_shared_bill(
    user,
    acting_store_id: str,
    *,
    company_id: str | None = None,
    tenant_container_id: str | None = None,
) -> bool:
    """Shared-bill access requires a domain policy and an explicit store grant."""
    if not can_access_store(
        user,
        acting_store_id,
        company_id=company_id,
        tenant_container_id=tenant_container_id,
    ):
        return False
    store = db.session.get(Store, acting_store_id)
    if store is None:
        return False
    if not can_access_data_domain(
        user,
        tenant_container_id=store.tenant_container_id,
        domain="open_bills",
        action="view",
        company_id=store.company_id,
        store_id=store.id,
    ):
        return False
    if getattr(user, "role", None) == "super_admin" or user.is_company_admin:
        return True
    return db.session.execute(
        select(UserStoreAssignment.id).where(
            UserStoreAssignment.tenant_container_id == store.tenant_container_id,
            UserStoreAssignment.user_id == user.id,
            UserStoreAssignment.company_id == store.company_id,
            UserStoreAssignment.store_id == acting_store_id,
            UserStoreAssignment.is_active.is_(True),
            UserStoreAssignment.can_view_shared_bills.is_(True),
        )
    ).scalar_one_or_none() is not None


def company_for_user(user) -> Company | None:
    if user is None:
        return None
    membership = current_membership(user)
    company_id = membership.company_id if membership is not None else user.company_id
    return db.session.get(Company, company_id) if company_id else None
