"""Read-only LCD order display."""

from flask import Blueprint

display_bp = Blueprint("display", __name__, template_folder="templates")

from . import routes  # noqa: E402
