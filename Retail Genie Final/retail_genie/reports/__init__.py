"""Activity logs and operational reports."""

from flask import Blueprint

reports_bp = Blueprint("reports", __name__, template_folder="templates")

from . import routes  # noqa: E402
