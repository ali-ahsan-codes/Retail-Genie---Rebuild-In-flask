"""Login, logout, own-account settings, and safe current-user API."""

from flask import Blueprint, flash, jsonify, redirect, render_template, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..models import User, normalize_username
from .forms import LoginForm, PasswordChangeForm

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
        if user and user.is_active and user.check_password(form.password.data or ""):
            # Rotate the signed session cookie; auth_version invalidates older account sessions.
            session.clear()
            session.permanent = True
            login_user(user, remember=False, fresh=True)
            session["auth_version"] = user.auth_version
            db.session.commit()  # Persist an Argon2 rehash if the hash parameters were upgraded.
            if user.force_password_change:
                return redirect(url_for("auth.change_password"))
            return redirect(url_for("main.dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("auth/login.html", form=form)


@auth_bp.post("/logout")
@login_required
def logout():
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
            # Keep this session signed in; all other sessions are now stale.
            session["auth_version"] = current_user.auth_version
            flash("Password updated. Other signed-in sessions have been invalidated.", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("auth/change_password.html", form=form)


@auth_bp.get("/api/v1/me")
@login_required
def current_account():
    return jsonify(current_user.to_public_dict())
