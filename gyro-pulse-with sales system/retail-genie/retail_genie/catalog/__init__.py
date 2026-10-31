"""Tenant-scoped catalog and inventory workflows."""

from flask import Blueprint

catalog_bp = Blueprint("catalog", __name__)

from . import routes as _routes  # noqa: E402,F401
