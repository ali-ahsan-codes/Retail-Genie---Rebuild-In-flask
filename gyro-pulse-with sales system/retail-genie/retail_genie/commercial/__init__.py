"""Demand notices and customer quotation workflows."""

from flask import Blueprint

commercial_bp = Blueprint("commercial", __name__)

from . import routes as _routes  # noqa: E402,F401
