"""Database-backed backup queue and the single-instance scheduler worker."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app
from sqlalchemy import and_, or_, text

from ..extensions import db
from ..models.backup import BackupRun, BackupSettings
from ..models.user import utc_now
from .service import BackupError, create_mysql_backup, prune_retained_backups

logger = logging.getLogger(__name__)


def get_or_create_settings() -> BackupSettings:
    settings = db.session.get(BackupSettings, 1)
    if settings is not None:
        return settings

    settings = BackupSettings(id=1)
    db.session.add(settings)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        settings = db.session.get(BackupSettings, 1)
        if settings is None:
            raise
    return settings


def normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def queue_manual_backup(requested_by_id: str | None = None) -> tuple[BackupRun | None, bool]:
    """Queue at most one outstanding backup and return (run, newly_queued)."""
    outstanding = (
        BackupRun.query.filter(BackupRun.status.in_(("queued", "running")))
        .order_by(BackupRun.requested_at.asc())
        .first()
    )
    if outstanding is not None:
        return outstanding, False

    run = BackupRun(trigger_type="manual", requested_by_id=requested_by_id)
    db.session.add(run)
    db.session.commit()
    return run, True


def recover_abandoned_runs() -> int:
    """Mark interrupted worker runs failed after the configured dump timeout."""
    timeout = max(1, int(current_app.config.get("BACKUP_TIMEOUT_SECONDS", 7200)))
    poll = max(1, int(current_app.config.get("BACKUP_SCHEDULER_POLL_SECONDS", 15)))
    cutoff = utc_now() - timedelta(seconds=timeout + poll + 60)
    abandoned = (
        BackupRun.query.filter_by(status="running")
        .filter(
            or_(
                BackupRun.started_at <= cutoff,
                and_(BackupRun.started_at.is_(None), BackupRun.requested_at <= cutoff),
            )
        )
        .all()
    )
    for run in abandoned:
        run.status = "failed"
        run.finished_at = utc_now()
        run.error_message = "Backup worker stopped before the run completed."
    if abandoned:
        db.session.commit()
        logger.error("Marked %s abandoned backup run(s) as failed", len(abandoned))
    return len(abandoned)


def queue_due_backup() -> str | None:
    """Return the next queued run, creating one if the schedule is due."""
    recover_abandoned_runs()
    queued = (
        BackupRun.query.filter_by(status="queued")
        .order_by(BackupRun.requested_at.asc())
        .first()
    )
    if queued is not None:
        return queued.id

    if BackupRun.query.filter_by(status="running").first() is not None:
        return None

    settings = get_or_create_settings()
    now = utc_now()
    next_run = normalize_utc(settings.next_run_at)
    if not settings.enabled or (next_run is not None and next_run > now):
        return None

    run = BackupRun(trigger_type="scheduled")
    settings.next_run_at = now + timedelta(minutes=settings.interval_minutes)
    db.session.add(run)
    db.session.commit()
    return run.id


def execute_backup_run(run_id: str) -> bool:
    """Run a queued backup and persist a success or failure audit record."""
    run = db.session.get(BackupRun, run_id)
    if run is None or run.status != "queued":
        return False

    run.status = "running"
    run.started_at = utc_now()
    db.session.commit()
    try:
        artifact = create_mysql_backup()
    except BackupError as exc:
        logger.warning("MySQL backup run %s failed: %s", run_id, exc)
        db.session.rollback()
        failed_run = db.session.get(BackupRun, run_id)
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.finished_at = utc_now()
            failed_run.error_message = str(exc)[:2000]
            db.session.commit()
        return False
    except Exception:
        logger.exception("Unexpected error while executing backup run %s", run_id)
        db.session.rollback()
        failed_run = db.session.get(BackupRun, run_id)
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.finished_at = utc_now()
            failed_run.error_message = "Unexpected backup worker error; see server logs."
            db.session.commit()
        return False

    completed_run = db.session.get(BackupRun, run_id)
    if completed_run is None:
        logger.error("Backup run %s disappeared before completion was recorded", run_id)
        return False
    completed_run.status = "succeeded"
    completed_run.finished_at = utc_now()
    completed_run.file_name = artifact.file_name
    completed_run.file_size_bytes = artifact.file_size_bytes
    completed_run.sha256 = artifact.sha256
    completed_run.file_retained = True
    completed_run.error_message = None
    db.session.commit()

    settings = get_or_create_settings()
    try:
        prune_retained_backups(settings.retention_count)
    except Exception:
        logger.exception("Could not apply backup retention after run %s", run_id)
    return True


def _scheduler_lock_name(app: Any) -> str:
    name = str(app.config.get("BACKUP_LOCK_NAME") or "").strip()
    return (name or "retail_genie_backup_scheduler")[:64]


def _acquire_scheduler_lock(connection: Any, lock_name: str) -> bool:
    lock_name = lock_name[:64]
    acquired = connection.execute(
        text("SELECT GET_LOCK(:lock_name, 0)"), {"lock_name": lock_name}
    ).scalar_one_or_none()
    return acquired == 1


def run_backup_scheduler(app: Any, *, once: bool = False) -> None:
    """Run the scheduled worker, protected by a MySQL advisory lock.

    The worker is a separate process by design; starting it from Flask web
    workers would cause duplicate schedulers under common WSGI deployments.
    """
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    if not database_uri:
        raise RuntimeError("DATABASE_URL is not configured.")

    from sqlalchemy.engine import make_url

    dialect = make_url(database_uri).get_backend_name()
    if dialect not in {"mysql", "mariadb"}:
        raise RuntimeError("The backup scheduler requires a MySQL or MariaDB database.")

    with app.app_context():
        lock_connection = db.engine.connect()
    lock_acquired = False
    try:
        lock_name = _scheduler_lock_name(app)
        lock_acquired = _acquire_scheduler_lock(lock_connection, lock_name)
        if not lock_acquired:
            raise RuntimeError("Another backup scheduler is already running for this database.")

        poll_seconds = max(1, int(app.config.get("BACKUP_SCHEDULER_POLL_SECONDS", 15)))
        while True:
            with app.app_context():
                try:
                    run_id = queue_due_backup()
                    if run_id is not None:
                        execute_backup_run(run_id)
                finally:
                    db.session.remove()

            if once:
                return
            time.sleep(poll_seconds)
    finally:
        if lock_acquired:
            try:
                lock_connection.execute(
                    text("SELECT RELEASE_LOCK(:lock_name)"),
                    {"lock_name": _scheduler_lock_name(app)},
                )
            except Exception:
                logger.exception("Could not release MySQL backup scheduler lock")
        lock_connection.close()
