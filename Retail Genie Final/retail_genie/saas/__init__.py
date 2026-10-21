"""SaaS productization: plan catalog, managed subscriptions, and tenant portal."""

from flask import Blueprint

saas_bp = Blueprint("saas", __name__)

from . import routes  # noqa: E402,F401
