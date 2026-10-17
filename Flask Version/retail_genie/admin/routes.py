"""First milestone account administration backed by the shared MySQL database."""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import PERMISSIONS, PERMISSION_LABELS, ROLE_PERMISSION_LIMITS, ROLES, User, normalize_username
from ..auth.permissions import permission_required
from .forms import CreateUserForm

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
ROLE_LABELS = {
    "admin": "Administrator",
    "manager": "Manager",
    "salesperson": "Salesperson",
    "storekeeper": "Storekeeper",
    "cashier": "Cashier",
    "logistics": "Logistics",
    "auditor": "Auditor",
    "display": "Display",
    "express": "Express checkout",
}


def _assignable_roles() -> list[str]:
    if current_user.role == "admin":
        return list(ROLES)
    return [role for role in ROLES if role not in {"admin", "manager"}]


def _assignable_permissions() -> list[str]:
    if current_user.role == "admin":
        return list(PERMISSIONS)
    return sorted(set(current_user.permissions or []))


def _render_accounts(form: CreateUserForm, status: int = 200):
    users = User.query.order_by(User.username.asc()).all()
    return render_template(
        "admin/users.html",
        form=form,
        users=users,
        role_labels=ROLE_LABELS,
        permission_labels=PERMISSION_LABELS,
    ), status


@admin_bp.route("/users", methods=["GET", "POST"])
@permission_required("manage_users")
def users():
    form = CreateUserForm()
    assignable_roles = _assignable_roles()
    assignable_permissions = _assignable_permissions()
    form.role.choices = [(role, ROLE_LABELS[role]) for role in assignable_roles]
    form.permissions.choices = [(permission, PERMISSION_LABELS[permission]) for permission in assignable_permissions]

    if form.validate_on_submit():
        username = normalize_username(form.username.data or "")
        role = form.role.data
        permissions = set(form.permissions.data or [])

        if role not in assignable_roles:
            form.role.errors.append("You cannot assign this role.")
            return _render_accounts(form, 400)
        if role not in ROLE_PERMISSION_LIMITS or not permissions.issubset(ROLE_PERMISSION_LIMITS[role]):
            form.permissions.errors.append("One or more permissions are not valid for this role.")
            return _render_accounts(form, 400)
        if current_user.role != "admin" and not permissions.issubset(set(current_user.permissions or [])):
            form.permissions.errors.append("You can only grant permissions that you already hold.")
            return _render_accounts(form, 403)
        if User.query.filter_by(username=username).first():
            form.username.errors.append("That username is already in use.")
            return _render_accounts(form, 400)

        account = User(
            username=username,
            role=role,
            permissions=sorted(permissions),
            force_password_change=True,
        )
        account.set_password(form.password.data or "")
        db.session.add(account)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("That username is already in use.")
            return _render_accounts(form, 400)

        flash(f"Account '{username}' created. Ask the user to change the temporary password after signing in.", "success")
        return redirect(url_for("admin.users"))

    return _render_accounts(form)


@admin_bp.post("/users/<string:user_id>/toggle-active")
@permission_required("manage_users")
def toggle_user_active(user_id: str):
    target = db.session.get(User, user_id)
    if target is None:
        return render_template("errors/404.html"), 404
    if target.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    if current_user.role != "admin" and target.role in {"admin", "manager"}:
        flash("Managers cannot change administrator or manager accounts.", "error")
        return redirect(url_for("admin.users"))

    if target.role == "admin" and target.is_active:
        active_admins = User.query.filter_by(role="admin", is_active=True).count()
        if active_admins <= 1:
            flash("The last active administrator cannot be deactivated.", "error")
            return redirect(url_for("admin.users"))

    target.is_active = not target.is_active
    target.auth_version += 1
    db.session.commit()
    state = "activated" if target.is_active else "deactivated"
    flash(f"Account '{target.username}' {state}.", "success")
    return redirect(url_for("admin.users"))
