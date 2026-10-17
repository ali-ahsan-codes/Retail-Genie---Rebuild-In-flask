from datetime import timedelta
import gzip
import hashlib
import subprocess
from pathlib import Path

import pytest

from retail_genie.backups import service
from retail_genie.backups.scheduler import (
    execute_backup_run,
    get_or_create_settings,
    normalize_utc,
    queue_due_backup,
    queue_manual_backup,
)
from retail_genie.extensions import db
from retail_genie.models.backup import BackupRun, BackupSettings
from retail_genie.models.user import utc_now


def _sign_in(client, username, password="A-long-test-password-4!"):
    return client.post("/login", data={"username": username, "password": password})


def test_backup_settings_are_visible_only_to_administrators(app, client, create_user):
    create_user("backup.admin", role="admin")
    _sign_in(client, "backup.admin")

    response = client.get("/admin/backups/")

    assert response.status_code == 200
    assert b"Database backups" in response.data
    assert b"Queue backup now" in response.data


def test_manager_cannot_configure_or_queue_database_backups(app, create_user):
    client = app.test_client()
    create_user("backup.manager", role="manager", permissions=["manage_settings"])
    _sign_in(client, "backup.manager")

    assert client.get("/admin/backups/").status_code == 403
    assert client.post("/admin/backups/run").status_code == 403


def test_admin_can_set_interval_and_retention(app, create_user):
    client = app.test_client()
    create_user("backup.admin", role="admin")
    _sign_in(client, "backup.admin")

    response = client.post(
        "/admin/backups/",
        data={"enabled": "y", "interval_minutes": "60", "retention_count": "9", "submit": "Save"},
    )

    assert response.status_code == 302
    with app.app_context():
        settings = db.session.get(BackupSettings, 1)
        assert settings.enabled is True
        assert settings.interval_minutes == 60
        assert settings.retention_count == 9
        assert settings.updated_by_id is not None
        assert settings.next_run_at is not None


def test_backup_interval_validation_rejects_values_outside_supported_range(app, create_user):
    client = app.test_client()
    create_user("backup.admin", role="admin")
    _sign_in(client, "backup.admin")

    response = client.post(
        "/admin/backups/",
        data={"enabled": "y", "interval_minutes": "5", "retention_count": "9"},
    )

    assert response.status_code == 400
    with app.app_context():
        settings = db.session.get(BackupSettings, 1)
        assert settings.enabled is False
        assert settings.interval_minutes == 1440
        assert settings.retention_count == 14


def test_manual_backup_requests_are_queued_once(app, create_user):
    client = app.test_client()
    create_user("backup.admin", role="admin")
    _sign_in(client, "backup.admin")

    first = client.post("/admin/backups/run")
    second = client.post("/admin/backups/run")

    assert first.status_code == second.status_code == 302
    with app.app_context():
        runs = BackupRun.query.filter_by(trigger_type="manual").all()
        assert len(runs) == 1
        assert runs[0].status == "queued"
        assert runs[0].requested_by_id is not None


def test_backup_service_writes_private_atomic_gzip_and_keeps_secret_out_of_argv(app, tmp_path, monkeypatch):
    backup_dir = tmp_path / "private-backups"
    monkeypatch.setitem(app.config, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setitem(
        app.config,
        "SQLALCHEMY_DATABASE_URI",
        "mysql+pymysql://app_user:AppPassword@db.example:3307/retail_genie?charset=utf8mb4",
    )
    monkeypatch.setitem(
        app.config,
        "BACKUP_DATABASE_URL",
        "mysql+pymysql://backup_user:Safe%21Pass%5Cword@db.example:3307/retail_genie?charset=utf8mb4",
    )
    captured = {}

    def fake_run(command, *, stdout, stderr, timeout, check, shell):
        captured["command"] = command
        captured["timeout"] = timeout
        option_path = Path(command[1].split("=", 1)[1])
        captured["option_path"] = option_path
        option_text = option_path.read_text(encoding="utf-8")
        assert 'user="backup_user"' in option_text
        assert 'password="Safe!Pass\\\\word"' in option_text
        stdout.write(b"-- generated SQL dump\nCREATE DATABASE retail_genie;\n")
        return subprocess.CompletedProcess(command, 0, stdout=None, stderr=b"")

    monkeypatch.setattr(service, "_mysqldump_executable", lambda: "/usr/bin/mysqldump")
    monkeypatch.setattr(service.subprocess, "run", fake_run)

    with app.app_context():
        artifact = service.create_mysql_backup()

    assert "Safe!Pass" not in " ".join(captured["command"])
    assert "AppPassword" not in " ".join(captured["command"])
    assert captured["timeout"] == 7200
    assert not captured["option_path"].exists()
    assert artifact.sha256 == hashlib.sha256((backup_dir / artifact.file_name).read_bytes()).hexdigest()
    assert gzip.decompress((backup_dir / artifact.file_name).read_bytes()).startswith(b"-- generated SQL dump")
    assert (backup_dir.stat().st_mode & 0o777) == 0o700
    assert ((backup_dir / artifact.file_name).stat().st_mode & 0o777) == 0o600
    assert list(backup_dir.glob("*.partial")) == []


def test_backup_service_rejects_public_static_directory(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "BACKUP_DIR", str(Path(app.static_folder) / "unpublished-backups"))
    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", "mysql+pymysql://backup:secret@db.example/retail_genie")
    monkeypatch.setitem(app.config, "BACKUP_DATABASE_URL", None)
    monkeypatch.setattr(service, "_mysqldump_executable", lambda: "/usr/bin/mysqldump")

    with app.app_context(), pytest.raises(service.BackupError, match="outside Flask's public static"):
        service.create_mysql_backup()


def test_backup_service_redacts_dump_errors_and_cleans_partial_files(app, tmp_path, monkeypatch):
    backup_dir = tmp_path / "private-backups"
    monkeypatch.setitem(app.config, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", "mysql+pymysql://backup:SensitivePass@db.example/retail_genie")
    monkeypatch.setitem(app.config, "BACKUP_DATABASE_URL", None)

    def failing_run(command, *, stdout, stderr, timeout, check, shell):
        stdout.write(b"partial dump data")
        return subprocess.CompletedProcess(command, 1, stdout=None, stderr=b"connection failed for SensitivePass")

    monkeypatch.setattr(service, "_mysqldump_executable", lambda: "/usr/bin/mysqldump")
    monkeypatch.setattr(service.subprocess, "run", failing_run)

    with app.app_context(), pytest.raises(service.BackupError) as error:
        service.create_mysql_backup()

    assert "SensitivePass" not in str(error.value)
    assert list(backup_dir.glob("*.sql.gz")) == []
    assert list(backup_dir.glob(".*.partial")) == []
    assert list(Path(app.instance_path).glob(".mysql-backup-*.cnf")) == []


def test_backup_service_timeout_cleans_partial_artifacts(app, tmp_path, monkeypatch):
    backup_dir = tmp_path / "private-backups"
    monkeypatch.setitem(app.config, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", "mysql+pymysql://backup:secret@db.example/retail_genie")
    monkeypatch.setitem(app.config, "BACKUP_DATABASE_URL", None)

    def timeout_run(command, *, stdout, stderr, timeout, check, shell):
        stdout.write(b"incomplete dump")
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(service, "_mysqldump_executable", lambda: "/usr/bin/mysqldump")
    monkeypatch.setattr(service.subprocess, "run", timeout_run)

    with app.app_context(), pytest.raises(service.BackupError, match="time limit"):
        service.create_mysql_backup()

    assert list(backup_dir.glob("*.sql.gz")) == []
    assert list(backup_dir.glob(".*.partial")) == []


def test_backup_service_rejects_a_dump_url_for_a_different_database(app, monkeypatch):
    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", "mysql+pymysql://app:secret@db.example/retail_genie")
    monkeypatch.setitem(app.config, "BACKUP_DATABASE_URL", "mysql+pymysql://backup:secret@other-db.example/retail_genie")
    monkeypatch.setattr(service, "_mysqldump_executable", lambda: "/usr/bin/mysqldump")

    with app.app_context(), pytest.raises(service.BackupError, match="same MySQL server and database"):
        service.create_mysql_backup()


def test_backup_service_rejects_sqlite_database_url(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", "sqlite://")
    monkeypatch.setitem(app.config, "BACKUP_DATABASE_URL", None)

    with app.app_context(), pytest.raises(service.BackupError, match="require a MySQL"):
        service.create_mysql_backup()


def test_scheduler_cli_refuses_non_mysql_targets(app):
    result = app.test_cli_runner().invoke(args=["backup-scheduler", "--once"])

    assert result.exit_code != 0
    assert "requires a MySQL or MariaDB" in result.output


def test_scheduler_queues_due_run_and_advances_next_run(app):
    with app.app_context():
        settings = get_or_create_settings()
        settings.enabled = True
        settings.interval_minutes = 30
        settings.next_run_at = utc_now() - timedelta(minutes=1)
        db.session.commit()

        first_id = queue_due_backup()
        second_id = queue_due_backup()
        run = db.session.get(BackupRun, first_id)

        assert first_id == second_id
        assert run.trigger_type == "scheduled"
        assert run.status == "queued"
        assert normalize_utc(settings.next_run_at) > utc_now()


def test_scheduler_marks_abandoned_runs_failed_and_continues(app, monkeypatch):
    monkeypatch.setitem(app.config, "BACKUP_TIMEOUT_SECONDS", 60)
    monkeypatch.setitem(app.config, "BACKUP_SCHEDULER_POLL_SECONDS", 1)
    with app.app_context():
        abandoned = BackupRun(
            status="running",
            trigger_type="scheduled",
            requested_at=utc_now() - timedelta(minutes=5),
            started_at=utc_now() - timedelta(minutes=5),
        )
        db.session.add(abandoned)
        db.session.commit()
        abandoned_id = abandoned.id

        assert queue_due_backup() is None
        recovered = db.session.get(BackupRun, abandoned_id)
        assert recovered.status == "failed"
        assert "stopped" in recovered.error_message


def test_backup_worker_records_a_safe_failure_status(app, monkeypatch):
    from retail_genie.backups import scheduler
    from retail_genie.backups.service import BackupError

    with app.app_context():
        run, queued = queue_manual_backup()
        assert queued is True
        run_id = run.id

    def failing_backup():
        raise BackupError("mysqldump utility was not found")

    monkeypatch.setattr(scheduler, "create_mysql_backup", failing_backup)
    with app.app_context():
        assert execute_backup_run(run_id) is False
        failed = db.session.get(BackupRun, run_id)
        assert failed.status == "failed"
        assert failed.finished_at is not None
        assert "mysqldump" in failed.error_message


def test_successful_backup_applies_retention_but_keeps_audit_rows(app, tmp_path, monkeypatch):
    from retail_genie.backups import scheduler
    from retail_genie.backups.service import BackupArtifact

    monkeypatch.setitem(app.config, "BACKUP_DIR", str(tmp_path / "backup"))
    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", "mysql+pymysql://backup:secret@db.example/retail_genie")
    backup_dir = Path(app.config["BACKUP_DIR"])
    backup_dir.mkdir()
    old_file = backup_dir / "older.sql.gz"
    old_file.write_bytes(b"old")

    with app.app_context():
        settings = get_or_create_settings()
        settings.retention_count = 1
        old_run = BackupRun(
            status="succeeded",
            trigger_type="scheduled",
            requested_at=utc_now() - timedelta(days=2),
            finished_at=utc_now() - timedelta(days=2),
            file_name=old_file.name,
            file_size_bytes=3,
            sha256="0" * 64,
            file_retained=True,
        )
        db.session.add(old_run)
        db.session.commit()
        old_run_id = old_run.id
        new_run, queued = queue_manual_backup()
        assert queued is True
        new_run_id = new_run.id

    def fake_backup():
        new_file = backup_dir / "newer.sql.gz"
        new_file.write_bytes(b"new")
        return BackupArtifact(new_file.name, 3, "1" * 64)

    monkeypatch.setattr(scheduler, "create_mysql_backup", fake_backup)
    with app.app_context():
        assert execute_backup_run(new_run_id) is True
        old_run = db.session.get(BackupRun, old_run_id)
        new_run = db.session.get(BackupRun, new_run_id)
        assert old_run.file_retained is False
        assert old_run.status == "succeeded"
        assert new_run.status == "succeeded"
        assert new_run.sha256 == "1" * 64
        assert old_file.exists() is False
        assert (backup_dir / "newer.sql.gz").exists()
