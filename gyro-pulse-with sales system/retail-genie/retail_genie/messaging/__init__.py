"""Internal messaging between container members."""

from flask import Blueprint

messaging_bp = Blueprint("messaging", __name__, template_folder="templates")

from . import routes  # noqa: E402
