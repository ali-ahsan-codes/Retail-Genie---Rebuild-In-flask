"""Personal cloud files and admin file management."""

from flask import Blueprint

cloud_bp = Blueprint("cloud", __name__, template_folder="templates")

from . import routes  # noqa: E402
