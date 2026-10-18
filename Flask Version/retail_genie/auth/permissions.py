"""Reusable server-side permission guards."""

from functools import wraps
from typing import Callable, TypeVar, cast

from flask import abort
from flask_login import current_user, login_required

View = TypeVar("View", bound=Callable)


def permission_required(permission: str):
    """Require an authenticated account and a permission checked from MySQL."""
    def decorator(view: View) -> View:
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_permission(permission):
                abort(403)
            return view(*args, **kwargs)

        return cast(View, wrapped)

    return decorator


def admin_required(view: View) -> View:
    """Require a tenant or platform administrator."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return cast(View, wrapped)


def super_admin_required(view: View) -> View:
    """Require the global Main Admin; tenant admins cannot cross companies."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_super_admin:
            abort(403)
        return view(*args, **kwargs)

    return cast(View, wrapped)


def company_admin_required(view: View) -> View:
    """Require a company admin or the global Main Admin."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (current_user.is_company_admin or current_user.is_super_admin):
            abort(403)
        return view(*args, **kwargs)

    return cast(View, wrapped)
