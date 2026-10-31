"""Create and prune compressed MySQL backups without exposing credentials."""

from __future__ import annotations

import gzip
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import current_app
from sqlalchemy.engine import URL, make_url

logger = logging.getLogger(__name__)


class BackupError(RuntimeError):
    """A backup could not be produced safely."""


@dataclass(frozen=True)
class BackupArtifact:
    file_name: str
    file_size_bytes: int
    sha256: str


def _backup_directory() -> Path:
    configured = Path(current_app.config["BACKUP_DIR"]).expanduser()
    if not configured.is_absolute():
        configured = Path(current_app.root_path).parent / configured
    directory = configured.resolve()

    static_folder = Path(current_app.static_folder).resolve()
    if directory == static_folder or static_folder in directory.parents:
        raise BackupError("BACKUP_DIR must be outside Flask's public static directory.")

    try:
        directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            directory.chmod(0o700)
            if directory.stat().st_mode & 0o077:
                raise BackupError("The configured backup directory is not private.")
    except OSError as exc:
        raise BackupError("The configured backup directory is unavailable or cannot be secured.") from exc
    return directory


def _option_value(value: str) -> str:
    if "\x00" in value:
        raise BackupError("The MySQL connection settings contain an unsupported null byte.")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{escaped}"'


def _socket_path(url: URL) -> str | None:
    socket = url.query.get("unix_socket")
    if isinstance(socket, tuple):
        socket = socket[0] if socket else None
    return str(socket) if socket else None


def _database_identity(url: URL) -> tuple[str, ...]:
    socket = _socket_path(url)
    if socket:
        return (url.get_backend_name(), "socket", socket, url.database or "")
    return (
        url.get_backend_name(),
        "host",
        (url.host or "localhost").casefold(),
        str(url.port or 3306),
        url.database or "",
    )


def _mysql_connection_options(url: URL) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = []
    socket = _socket_path(url)

    if url.username:
        options.append(("user", url.username))
    if url.password is not None:
        options.append(("password", url.password))
    if socket:
        options.append(("socket", str(socket)))
    else:
        if url.host:
            options.append(("host", url.host))
        if url.port:
            options.append(("port", str(url.port)))

    # Preserve common TLS settings passed to PyMySQL in DATABASE_URL. The MySQL
    # client uses hyphenated option names in its option files.
    tls_options = {
        "ssl_ca": "ssl-ca",
        "ssl_cert": "ssl-cert",
        "ssl_key": "ssl-key",
    }
    for query_name, option_name in tls_options.items():
        value = url.query.get(query_name)
        if isinstance(value, tuple):
            value = value[0] if value else None
        if value:
            options.append((option_name, str(value)))
    return options


def _write_mysql_defaults_file(url: URL) -> Path:
    instance_dir = Path(current_app.instance_path)
    descriptor = -1
    path: Path | None = None
    try:
        instance_dir.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".mysql-backup-", suffix=".cnf", dir=instance_dir)
        path = Path(name)
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
            if os.fstat(descriptor).st_mode & 0o077:
                raise BackupError("The MySQL option file is not private.")
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as options_file:
            descriptor = -1
            options_file.write("[client]\n")
            for key, value in _mysql_connection_options(url):
                options_file.write(f"{key}={_option_value(value)}\n")
        return path
    except (OSError, BackupError) as exc:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove incomplete MySQL option file")
        raise BackupError("Could not securely prepare MySQL client credentials.") from exc


def _mysqldump_executable() -> str:
    configured = str(current_app.config.get("MYSQLDUMP_PATH", "mysqldump")).strip()
    if not configured:
        raise BackupError("MYSQLDUMP_PATH is empty; configure the MySQL client utility.")
    if Path(configured).is_file():
        return configured
    executable = shutil.which(configured)
    if executable is None:
        raise BackupError("The mysqldump utility was not found. Install the MySQL client tools or set MYSQLDUMP_PATH.")
    return executable


def create_mysql_backup() -> BackupArtifact:
    """Dump the configured MySQL database to an atomic, private gzip file."""
    database_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    if not database_uri:
        raise BackupError("DATABASE_URL is not configured.")
    backup_uri = current_app.config.get("BACKUP_DATABASE_URL") or database_uri

    try:
        application_url = make_url(database_uri)
        url = make_url(backup_uri)
    except (TypeError, ValueError) as exc:
        raise BackupError("DATABASE_URL or BACKUP_DATABASE_URL is not a valid SQLAlchemy URL.") from exc
    if application_url.get_backend_name() not in {"mysql", "mariadb"} or url.get_backend_name() not in {"mysql", "mariadb"}:
        raise BackupError("Automatic database backups require a MySQL or MariaDB DATABASE_URL.")
    if not application_url.database or not url.database:
        raise BackupError("DATABASE_URL and BACKUP_DATABASE_URL must include a database name.")
    if _database_identity(application_url) != _database_identity(url):
        raise BackupError("BACKUP_DATABASE_URL must point to the same MySQL server and database as DATABASE_URL.")

    executable = _mysqldump_executable()
    backup_dir = _backup_directory()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"retail-genie-{timestamp}-{uuid4().hex[:8]}.sql.gz"
    final_path = backup_dir / file_name
    temporary_path = backup_dir / f".{file_name}.partial"
    defaults_file = _write_mysql_defaults_file(url)

    command = [
        executable,
        f"--defaults-extra-file={defaults_file}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--events",
        "--triggers",
        "--hex-blob",
        "--no-tablespaces",
        "--default-character-set=utf8mb4",
        "--databases",
        url.database,
    ]
    timeout = max(1, int(current_app.config.get("BACKUP_TIMEOUT_SECONDS", 7200)))
    backup_complete = False
    try:
        with temporary_path.open("xb") as raw_output:
            with gzip.GzipFile(fileobj=raw_output, mode="wb", mtime=0) as compressed_output:
                completed = subprocess.run(
                    command,
                    stdout=compressed_output,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                    check=False,
                    shell=False,
                )
        if completed.returncode != 0:
            stderr = completed.stderr or b""
            if isinstance(stderr, bytes):
                stderr_text = stderr.decode("utf-8", errors="replace")
            else:
                stderr_text = str(stderr)
            if url.password:
                stderr_text = stderr_text.replace(url.password, "[redacted]")
            stderr_text = re.sub(r"(?i)(password\s*[=:]\s*)\S+", r"\1[redacted]", stderr_text)
            detail = " ".join(stderr_text.split())[-800:]
            message = f"mysqldump exited with status {completed.returncode}."
            if detail:
                message = f"{message} {detail}"
            raise BackupError(message)

        try:
            uncompressed_size = 0
            with gzip.open(temporary_path, "rb") as compressed_backup:
                for chunk in iter(lambda: compressed_backup.read(1024 * 1024), b""):
                    uncompressed_size += len(chunk)
        except (gzip.BadGzipFile, EOFError, OSError, zlib.error) as exc:
            raise BackupError("mysqldump did not produce a complete, valid gzip database dump.") from exc
        if uncompressed_size == 0:
            raise BackupError("mysqldump produced an empty database dump.")

        if os.name != "nt":
            os.chmod(temporary_path, 0o600)
            if temporary_path.stat().st_mode & 0o077:
                raise BackupError("The completed backup file is not private.")
        os.replace(temporary_path, final_path)
        digest = hashlib.sha256()
        with final_path.open("rb") as backup_file:
            for chunk in iter(lambda: backup_file.read(1024 * 1024), b""):
                digest.update(chunk)
        artifact = BackupArtifact(
            file_name=file_name,
            file_size_bytes=final_path.stat().st_size,
            sha256=digest.hexdigest(),
        )
        backup_complete = True
        return artifact
    except subprocess.TimeoutExpired as exc:
        raise BackupError("mysqldump exceeded the configured backup time limit.") from exc
    except BackupError:
        raise
    except OSError as exc:
        logger.exception("Could not complete the MySQL backup file operation")
        raise BackupError("The backup could not be written to the configured backup directory.") from exc
    finally:
        cleanup_failed = False
        for temporary_file in (defaults_file, temporary_path):
            try:
                temporary_file.unlink(missing_ok=True)
            except OSError:
                cleanup_failed = True
                logger.exception("Could not remove a temporary backup file")
        if cleanup_failed or not backup_complete:
            try:
                final_path.unlink(missing_ok=True)
            except OSError:
                cleanup_failed = True
                logger.exception("Could not remove an incomplete backup artifact")
        if cleanup_failed:
            raise BackupError("Temporary backup files could not be removed; inspect the private app directories.")


def prune_retained_backups(retention_count: int) -> int:
    """Remove older successful dump files, retaining their audit rows."""
    from ..extensions import db
    from ..models.backup import BackupRun

    keep_count = max(1, int(retention_count))
    successful_runs = (
        BackupRun.query.filter_by(status="succeeded", file_retained=True)
        .filter(BackupRun.file_name.is_not(None))
        .order_by(BackupRun.finished_at.desc(), BackupRun.requested_at.desc())
        .all()
    )
    directory = _backup_directory()
    removed = 0
    for old_run in successful_runs[keep_count:]:
        # File names are generated by this service; still reject path components
        # in case a database value has been altered or imported unsafely.
        file_name = old_run.file_name or ""
        if Path(file_name).name != file_name or file_name in {"", ".", ".."}:
            logger.error("Skipping unsafe backup file name on run %s", old_run.id)
            continue
        try:
            (directory / file_name).unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove expired backup file for run %s", old_run.id)
            continue
        old_run.file_retained = False
        removed += 1
    if removed:
        db.session.commit()
    return removed
