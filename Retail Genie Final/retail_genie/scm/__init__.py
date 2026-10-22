"""Suppliers, purchase orders, receiving, and logistics."""

from flask import Blueprint

scm_bp = Blueprint("scm", __name__, template_folder="templates")

from . import routes  # noqa: E402
