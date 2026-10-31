"""Stock count audits with evidence images."""

from flask import Blueprint

stock_audits_bp = Blueprint("stock_audits", __name__, template_folder="templates")

from . import routes  # noqa: E402
