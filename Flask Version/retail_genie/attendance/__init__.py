"""Attendance punch-in and break tracking."""

from flask import Blueprint

attendance_bp = Blueprint("attendance", __name__, template_folder="templates")

from . import routes  # noqa: E402
