"""Login, tenant selection, own-account settings, and safe current-user API."""

from flask import Blueprint, flash, jsonify, redirect, render_template, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..models import TenantContainer, User, normalize_username
from .forms import LoginForm, PasswordChangeForm, SelectTenantForm
from .tenant_context import available_memberships, select_container_for_session

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        username = normalize_username(form.username.data or "")
        user = User.query.filter_by(username=username).first()
        memberships = available_memberships(user.id) if user and user.is_active and not user.is_super_admin else []
        tenant_is_active = bool(memberships) if user and not user.is_super_admin else bool(user and user.company_id is None)
        if user and user.is_active and tenant_is_active and user.check_password(form.password.data or ""):
            # Rotate the signed session cookie; auth_version invalidates older account sessions.
            session.clear()
            session.permanent = True
            login_user(user, remember=False, fresh=True)
            session["auth_version"] = user.auth_version
            if not user.is_super_admin:
                if len(memberships) == 1:
                    if not select_container_for_session(user, memberships[0].tenant_container_id):
                        logout_user()
                        session.clear()
                        flash("Invalid username or password.", "error")
                        return render_template("auth/login.html", form=form)
                else:
                    session["pending_tenant_selection"] = True
            db.session.commit()  # Persist an Argon2 rehash if the hash parameters were upgraded.
            if user.force_password_change:
                return redirect(url_for("auth.change_password"))
            if not user.is_super_admin and len(memberships) > 1:
                return redirect(url_for("auth.select_tenant"))
            return redirect(url_for("main.dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/account/tenant", methods=["GET", "POST"])
@login_required
def select_tenant():
    form = SelectTenantForm()
    if current_user.is_super_admin:
        containers = TenantContainer.query.filter_by(is_active=True).order_by(TenantContainer.name.asc()).all()
    else:
        containers = [
            db.session.get(TenantContainer, membership.tenant_container_id)
            for membership in available_memberships(current_user.id)
        ]
        containers = [container for container in containers if container is not None]
    choices = [(container.id, container.name) for container in containers]
    form.tenant_container_id.choices = choices
    if request_method_is_post(form):
        if form.validate_on_submit():
            if not select_container_for_session(current_user, form.tenant_container_id.data):
                form.tenant_container_id.errors.append("That workspace is no longer available to this account.")
            else:
                flash("Active tenant workspace changed.", "success")
                return redirect(url_for("main.dashboard"))
    elif choices:
        form.tenant_container_id.data = choices[0][0]
    return render_template("auth/select_tenant.html", form=form, containers=containers)


def request_method_is_post(form: SelectTenantForm) -> bool:
    """Small helper to keep GET defaults separate from WTForms validation."""
    from flask import request

    return request.method == "POST"


@auth_bp.post("/logout")
@login_required
def logout():
    from ..realtime.service import clear_user_subscriptions

    clear_user_subscriptions(current_user.id)
    logout_user()
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = PasswordChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data or ""):
            form.current_password.errors.append("Current password is incorrect.")
        else:
            current_user.set_password(form.new_password.data or "")
            current_user.force_password_change = False
            current_user.auth_version += 1
            db.session.commit()
            from ..realtime.service import clear_user_subscriptions

            clear_user_subscriptions(current_user.id)
            # Keep this session signed in; all other sessions are now stale.
            session["auth_version"] = current_user.auth_version
            flash("Password updated. Other signed-in sessions have been invalidated.", "success")
            if session.get("pending_tenant_selection"):
                return redirect(url_for("auth.select_tenant"))
            return redirect(url_for("main.dashboard"))

    return render_template("auth/change_password.html", form=form)


@auth_bp.get("/api/v1/me")
@login_required
def current_account():
    return jsonify(current_user.to_public_dict())
