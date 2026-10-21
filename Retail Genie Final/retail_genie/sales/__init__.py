"""Retail sales, shared open bills, payments, approvals, and manager cashups."""

from flask import Blueprint

sales_bp = Blueprint("sales", __name__)

from . import routes as _routes  # noqa: E402,F401
