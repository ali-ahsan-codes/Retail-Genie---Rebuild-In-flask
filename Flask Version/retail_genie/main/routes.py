"""Authenticated home/dashboard placeholder for migrated modules."""

from flask import Blueprint, render_template
from flask_login import login_required

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
@main_bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("main/dashboard.html")
