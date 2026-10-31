"""Restricted express checkout surface."""

from flask import Blueprint

express_bp = Blueprint("express", __name__, template_folder="templates")

from . import routes  # noqa: E402
