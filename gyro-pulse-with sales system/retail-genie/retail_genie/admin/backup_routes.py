"""Administrator-only backup schedule and audit-history pages."""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user

from ..auth.permissions import admin_required
from ..extensions import db
from ..models.backup import BackupRun
from ..models.user import utc_now
from ..backups.scheduler import get_or_create_settings, queue_manual_backup
from .backup_forms import BackupSettingsForm

backup_admin_bp = Blueprint("admin_backups", __name__, url_prefix="/admin/backups")


def _render_settings(form: BackupSettingsForm, status: int = 200):
    settings = get_or_create_settings()
    recent_runs = BackupRun.query.order_by(BackupRun.requested_at.desc()).limit(30).all()
    return render_template(
        "admin/backups.html",
        form=form,
        settings=settings,
        recent_runs=recent_runs,
        format_utc=format_utc,
    ), status


def format_utc(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


@backup_admin_bp.route("/", methods=["GET", "POST"])
@admin_required
def settings():
    backup_settings = get_or_create_settings()
    form = BackupSettingsForm(obj=backup_settings)

    if form.validate_on_submit():
        backup_settings.enabled = bool(form.enabled.data)
        backup_settings.interval_minutes = int(form.interval_minutes.data)
        backup_settings.retention_count = int(form.retention_count.data)
        backup_settings.updated_by_id = current_user.id
        backup_settings.next_run_at = (
            utc_now() + timedelta(minutes=backup_settings.interval_minutes)
            if backup_settings.enabled
            else None
        )
        db.session.commit()
        if backup_settings.enabled:
            flash("Automatic backups are enabled. The next run is scheduled after the selected interval.", "success")
        else:
            flash("Automatic backups are disabled. Existing backup files were not removed.", "info")
        return redirect(url_for("admin_backups.settings"))

    return _render_settings(form, 400 if form.is_submitted() else 200)


@backup_admin_bp.post("/run")
@admin_required
def run_now():
    _run, newly_queued = queue_manual_backup(current_user.id)
    if newly_queued:
        flash("A database backup has been queued. Check the run history for its result.", "success")
    else:
        flash("A backup is already queued or running.", "info")
    return redirect(url_for("admin_backups.settings"))
