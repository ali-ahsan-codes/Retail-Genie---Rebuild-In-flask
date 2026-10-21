"""Environment-driven configuration. Production secrets are never hard-coded."""

import os
from datetime import timedelta
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    SESSION_COOKIE_NAME = "retail_genie_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_REFRESH_EACH_REQUEST = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_LIFETIME_HOURS", "8")))

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = timedelta(hours=1)
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024

    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")

    # Backups are intentionally written outside Flask's static directory and are
    # never exposed by a download route. Override on shared/production hosts if
    # the app directory itself is not a suitable persistent storage location.
    BACKUP_DIR = os.getenv("BACKUP_DIR") or str(Path(__file__).resolve().parents[1] / "backup")
    # Uploads are private persistent files, never Flask static assets.
    UPLOADS_DIR = os.getenv("UPLOADS_DIR") or str(Path(__file__).resolve().parents[1] / "uploads")
    BACKUP_DATABASE_URL = os.getenv("BACKUP_DATABASE_URL") or None
    MYSQLDUMP_PATH = os.getenv("MYSQLDUMP_PATH", "mysqldump")
    BACKUP_TIMEOUT_SECONDS = int(os.getenv("BACKUP_TIMEOUT_SECONDS", "7200"))
    BACKUP_SCHEDULER_POLL_SECONDS = int(os.getenv("BACKUP_SCHEDULER_POLL_SECONDS", "15"))
    BACKUP_LOCK_NAME = os.getenv("BACKUP_LOCK_NAME", "retail_genie_backup_scheduler")

    # SMTP is opt-in. Commercial email actions fail clearly when not configured.
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_SENDER = os.getenv("SMTP_SENDER")
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_USE_TLS = _env_bool("SMTP_USE_TLS", True)
    SMTP_USE_SSL = _env_bool("SMTP_USE_SSL", False)
    SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))

    # Each WSGI worker polls the shared durable event table, then emits only to
    # its own local Socket.IO clients; replay remains the reconnect fallback.
    REALTIME_DISPATCH_ENABLED = _env_bool("REALTIME_DISPATCH_ENABLED", True)
    REALTIME_POLL_INTERVAL_SECONDS = float(os.getenv("REALTIME_POLL_INTERVAL_SECONDS", "0.5"))
    REALTIME_RETENTION_DAYS = int(os.getenv("REALTIME_RETENTION_DAYS", "30"))
    REALTIME_RETENTION_SWEEP_SECONDS = int(os.getenv("REALTIME_RETENTION_SWEEP_SECONDS", "21600"))
