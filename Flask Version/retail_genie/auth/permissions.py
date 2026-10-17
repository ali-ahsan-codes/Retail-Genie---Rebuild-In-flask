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
