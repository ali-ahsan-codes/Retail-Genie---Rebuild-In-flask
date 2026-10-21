"""Role- and tenant-scoped account administration."""

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth.permissions import permission_required
from ..auth.store_scope import accessible_store_ids
from ..auth.tenant_context import current_membership
from ..extensions import db
from ..models import (
    Company,
    ContainerMembership,
    PERMISSIONS,
    PERMISSION_LABELS,
    ROLE_PERMISSION_LIMITS,
    User,
    UserStoreAssignment,
    normalize_username,
)
from .forms import CreateUserForm
from ..saas.service import SaaSRuleError, ensure_capacity

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
ROLE_LABELS = {
    "super_admin": "Main Admin / Super Admin",
    "company_admin": "Company Admin / Sub Admin",
    "admin": "Company Admin (legacy)",
    "manager": "Manager",
    "salesperson": "Salesperson",
    "storekeeper": "Storekeeper",
    "cashier": "Cashier",
    "logistics": "Logistics",
    "auditor": "Auditor",
    "display": "Display",
    "express": "Express checkout",
}
_STAFF_ROLES = {"manager", "salesperson", "storekeeper", "cashier", "logistics", "auditor", "display", "express"}


def _assignable_roles() -> list[str]:
    if current_user.is_super_admin:
        return ["company_admin", *_STAFF_ROLES]
    if current_user.is_company_admin:
        return sorted(_STAFF_ROLES)
    return sorted(_STAFF_ROLES - {"manager"})


def _assignable_permissions() -> list[str]:
    if current_user.is_admin:
        return list(PERMISSIONS)
    membership = current_membership(current_user)
    permissions = membership.permissions if membership is not None else current_user.permissions
    return sorted(set(permissions or []))


def _visible_users(company_id: str | None):
    query = User.query
    if current_user.is_super_admin:
        if company_id:
            query = query.filter(User.company_id == company_id)
        return query.order_by(User.username.asc()).all()

    membership = current_membership(current_user)
    if membership is None or not membership.company_id or membership.company_id != company_id:
        return []
    if current_user.is_company_admin:
        query = query.filter(User.company_id == membership.company_id)
    else:
        allowed_store_ids = accessible_store_ids(current_user, company_id=membership.company_id)
        if not allowed_store_ids:
            return [current_user]
        allowed_user_ids = db.session.execute(
            select(UserStoreAssignment.user_id).where(
                UserStoreAssignment.tenant_container_id == membership.tenant_container_id,
                UserStoreAssignment.company_id == membership.company_id,
                UserStoreAssignment.store_id.in_(allowed_store_ids),
                UserStoreAssignment.is_active.is_(True),
            )
        ).scalars().all()
        query = query.filter(
            User.company_id == membership.company_id,
            User.id.in_(set(allowed_user_ids) | {current_user.id}),
        )
    return query.order_by(User.username.asc()).all()


def _target_membership(target: User) -> ContainerMembership | None:
    if current_user.is_super_admin:
        target_company = db.session.get(Company, target.company_id) if target.company_id else None
        if target_company is None:
            return None
        return current_membership(target, tenant_container_id=target_company.tenant_container_id)
    actor_membership = current_membership(current_user)
    if actor_membership is None:
        return None
    return current_membership(target, tenant_container_id=actor_membership.tenant_container_id)


def _can_manage_target(target: User) -> bool:
    if target.role == "super_admin":
        return False
    target_membership = _target_membership(target)
    if target_membership is None:
        return False
    if current_user.is_super_admin:
        return True
    actor_membership = current_membership(current_user)
    if actor_membership is None or target_membership.company_id != actor_membership.company_id:
        return False
    if current_user.is_company_admin:
        return True
    if target_membership.role in {"super_admin", "company_admin", "admin", "manager"}:
        return False
    actor_stores = accessible_store_ids(current_user, company_id=actor_membership.company_id)
    target_stores = accessible_store_ids(target, company_id=actor_membership.company_id)
    return bool(actor_stores & target_stores)


def _render_accounts(form: CreateUserForm, status: int = 200, company_id: str | None = None):
    users = _visible_users(company_id)
    return render_template(
        "admin/users.html",
        form=form,
        users=users,
        role_labels=ROLE_LABELS,
        permission_labels=PERMISSION_LABELS,
        companies=Company.query.filter_by(is_active=True).order_by(Company.name.asc()).all() if current_user.is_super_admin else [],
        company_names={company.id: company.name for company in Company.query.all()},
        selected_company_id=company_id,
        current_company_id=(current_membership(current_user).company_id if current_membership(current_user) else current_user.company_id),
    ), status


@admin_bp.route("/users", methods=["GET", "POST"])
@permission_required("manage_users")
def users():
    form = CreateUserForm()
    active_companies = Company.query.filter_by(is_active=True).order_by(Company.name.asc()).all()
    if current_user.is_super_admin:
        form.company_id.choices = [(company.id, company.name) for company in active_companies]
        company_id = form.company_id.data or active_companies[0].id if active_companies else None
        if company_id and not form.company_id.data:
            form.company_id.data = company_id
    else:
        actor_membership = current_membership(current_user)
        company_id = actor_membership.company_id if actor_membership else None
        company = db.session.get(Company, company_id) if company_id else None
        form.company_id.choices = [(company.id, company.name)] if company else []
        form.company_id.data = company.id if company else None

    assignable_roles = _assignable_roles()
    assignable_permissions = _assignable_permissions()
    form.role.choices = [(role, ROLE_LABELS[role]) for role in assignable_roles]
    form.permissions.choices = [(permission, PERMISSION_LABELS[permission]) for permission in assignable_permissions]

    if form.validate_on_submit():
        username = normalize_username(form.username.data or "")
        role = form.role.data
        permissions = set(form.permissions.data or [])
        actor_membership = current_membership(current_user)
        target_company_id = form.company_id.data if current_user.is_super_admin else (actor_membership.company_id if actor_membership else None)
        company = db.session.get(Company, target_company_id) if target_company_id else None

        if role not in assignable_roles:
            form.role.errors.append("You cannot assign this role.")
            return _render_accounts(form, 400, company_id)
        if current_user.is_super_admin and not target_company_id:
            form.company_id.errors.append("Choose a company for this account.")
            return _render_accounts(form, 400, company_id)
        if company is None or not company.is_active:
            form.company_id.errors.append("Choose an active company.")
            return _render_accounts(form, 400, company_id)
        if not current_user.is_super_admin and (actor_membership is None or company.tenant_container_id != actor_membership.tenant_container_id):
            abort(404)
        if role not in ROLE_PERMISSION_LIMITS or not permissions.issubset(ROLE_PERMISSION_LIMITS[role]):
            form.permissions.errors.append("One or more permissions are not valid for this role.")
            return _render_accounts(form, 400, company_id)
        actor_permissions = actor_membership.permissions if actor_membership is not None else current_user.permissions
        if not current_user.is_admin and not permissions.issubset(set(actor_permissions or [])):
            form.permissions.errors.append("You can only grant permissions that you already hold.")
            return _render_accounts(form, 403, company_id)
        if User.query.filter_by(username=username).first():
            form.username.errors.append("That username is already in use.")
            return _render_accounts(form, 400, company_id)
        try:
            ensure_capacity(company.tenant_container_id, "active_user")
        except SaaSRuleError as error:
            form.username.errors.append(str(error))
            return _render_accounts(form, 400, company_id)

        account = User(
            company_id=company.id,
            username=username,
            role=role,
            permissions=sorted(permissions),
            force_password_change=True,
        )
        account.set_password(form.password.data or "")
        db.session.add(account)
        db.session.flush()
        db.session.add(
            ContainerMembership(
                tenant_container_id=company.tenant_container_id,
                user_id=account.id,
                company_id=company.id,
                role=role,
                permissions=sorted(permissions),
                is_default=True,
                is_active=True,
            )
        )
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("That username is already in use.")
            return _render_accounts(form, 400, company_id)

        flash(
            f"Account '{username}' created. Assign it to its authorized store(s) before it can access store data.",
            "success",
        )
        return redirect(url_for("admin.users", company_id=company.id if current_user.is_super_admin else None))

    return _render_accounts(form, company_id=company_id)


@admin_bp.post("/users/<string:user_id>/toggle-active")
@permission_required("manage_users")
def toggle_user_active(user_id: str):
    target = db.session.get(User, user_id)
    if target is None or not _can_manage_target(target):
        return render_template("errors/404.html"), 404
    if target.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    if target.role == "super_admin":
        abort(403)

    membership = _target_membership(target)
    if membership is None:
        return render_template("errors/404.html"), 404
    if membership.role in {"company_admin", "admin"} and membership.is_active:
        active_company_admins = ContainerMembership.query.filter(
            ContainerMembership.tenant_container_id == membership.tenant_container_id,
            ContainerMembership.company_id == membership.company_id,
            ContainerMembership.role.in_(["company_admin", "admin"]),
            ContainerMembership.is_active.is_(True),
        ).count()
        if active_company_admins <= 1:
            flash("The last active Company Admin cannot be deactivated.", "error")
            return redirect(url_for("admin.users", company_id=membership.company_id if current_user.is_super_admin else None))

    if not membership.is_active:
        try:
            ensure_capacity(membership.tenant_container_id, "active_user")
        except SaaSRuleError as error:
            flash(str(error), "error")
            return redirect(url_for("admin.users", company_id=membership.company_id if current_user.is_super_admin else None))

    membership.is_active = not membership.is_active
    active_memberships = ContainerMembership.query.filter_by(user_id=target.id, is_active=True).count()
    target.is_active = membership.is_active or active_memberships > 0
    target.auth_version += 1
    from ..realtime.service import clear_user_subscriptions, publish_realtime_event, stage_user_access_revocations

    access_event_ids = stage_user_access_revocations(
        user_id=target.id,
        actor_user_id=current_user.id,
        include_inactive=True,
    )
    db.session.commit()
    for event_id in access_event_ids:
        publish_realtime_event(event_id)
    clear_user_subscriptions(target.id)
    state = "activated" if membership.is_active else "deactivated"
    flash(f"Account '{target.username}' {state} in this tenant.", "success")
    return redirect(url_for("admin.users", company_id=membership.company_id if current_user.is_super_admin else None))
