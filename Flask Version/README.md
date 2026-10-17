# Retail Genie — Flask Version

This directory is the **Node-free Flask rebuild**. Phase 1 supplies the Flask app factory, secure account authentication, server-side permissions, health endpoints, and tests. Phase 2 now adds administrator-configurable MySQL backups, a separate scheduler worker, a typed landing schema for the 27-table SQLite source, and a read-only dry-run / insert-only importer. The business modules, upload migration, live MySQL validation, and real-time business events are still outstanding. `Node Js Version/` remains the unchanged behavior reference.

The application does not use Node.js, npm, React, or a frontend build step. Flask serves the HTML templates and static CSS. The browser never connects directly to MySQL.

## Requirements

- Python 3.11 or newer
- MySQL 8.x (InnoDB, `utf8mb4`)
- MySQL client utilities including `mysqldump` on the Flask app host
- A long random Flask secret key

Create a MySQL database and a dedicated application user. Run these statements in MySQL, replacing the example password with a unique secret:

```sql
CREATE DATABASE retail_genie CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'retail_genie'@'localhost' IDENTIFIED BY 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';
GRANT ALL PRIVILEGES ON retail_genie.* TO 'retail_genie'@'localhost';
```

Keep MySQL bound to the office server; do not expose port 3306 to client devices or the public internet. Only the Flask server should connect to the database. For production, set `BACKUP_DATABASE_URL` to a restricted dump account with the metadata/read privileges required by your MySQL version for `mysqldump --routines --events --triggers`. It must target the same MySQL server and database as `DATABASE_URL`. If unset, backups use `DATABASE_URL` credentials. Validate the dump account against the office MySQL server.

## Local setup (PowerShell)

```powershell
cd "Flask Version"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` before starting. Set a strong `SECRET_KEY` (generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`) and update `DATABASE_URL` with the local MySQL credentials. URL-encode any special characters in the database password. `SESSION_COOKIE_SECURE=false` is only for local HTTP development; set it to `true` once the office deployment is served over HTTPS.

Initialize the schema and create the first administrator interactively:

```powershell
flask --app wsgi db upgrade
flask --app wsgi create-admin --username admin
python run.py
```

The create-admin command prompts for a password and confirmation. There is no default/demo account or password. Use a unique password of at least 12 characters.

Open `http://127.0.0.1:5000/`. Health endpoints are available at `/healthz` and `/readyz` (the latter checks the MySQL connection).

## Automatic database backups

Administrators can open **Database backups** at `/admin/backups/` and set an interval (15 minutes to 7 days), retention count (1–365 files), enable/disable the schedule, and queue a one-time run. The defaults are disabled, daily, and 14 files. The app writes private, gzip-compressed `.sql.gz` dumps to `Flask Version/backup/` by default (override with `BACKUP_DIR`). A SHA-256 checksum, file size, run status, and sanitized error are recorded in MySQL. Older successful files are removed according to the configured retention count; audit rows remain. The app does not provide a public backup download URL.

Run **one separate scheduler/worker process** on the Flask/MySQL host; do not start a scheduler in each WSGI web worker:

```powershell
# Foreground worker (keeps checking the MySQL schedule)
flask --app wsgi backup-scheduler

# One check, useful for deployment/smoke tests
flask --app wsgi backup-scheduler --once
```

The worker uses a MySQL advisory lock to refuse a second scheduler for the same database. Configure the OS service manager to restart the worker after a host restart; the office server OS has not been confirmed, so a production service definition is not supplied yet. The one-time “Queue backup now” button also requires this worker to be running. Install `mysqldump` on the app host, set `MYSQLDUMP_PATH` if it is not on `PATH`, and size `BACKUP_TIMEOUT_SECONDS` for the database. Credentials are passed through a short-lived, permission-restricted MySQL option file, not command-line arguments. On Windows, protect the backup folder with an account-specific filesystem ACL.

The backup directory is intentionally outside Flask's static directory, is ignored by Git, and is created with owner-only permissions on POSIX hosts. Keep it on persistent storage and arrange a separate encrypted/off-host copy for disaster recovery; a backup on the same server is not protection against disk loss. Test restores before production use.

## Phase 2 SQLite-to-MySQL import

The checked-in `Node Js Version/netpos.db` is confirmed **demo/sample data**, not the production dataset. The command below is a read-only dry run and is safe to use against that sample:

```powershell
flask --app wsgi import-sqlite --source "..\Node Js Version\netpos.db"
```

The importer requires the reviewed 27-table schema documented in `LEGACY_SCHEMA_MAP.md`, validates JSON, numeric precision, timestamps, usernames, permissions, and SQLite foreign keys, and reports table counts plus OMR order/payment, stock, and invoice-counter reconciliation totals. On apply, it verifies target row counts and foreign keys and aborts the transaction if those totals do not match. It opens the source read-only and immutable; it never writes to the SQLite file. For any real migration, first make a verified, consistent SQLite backup. Close/checkpoint the source so committed WAL contents are included; do not point the importer at a live database or at a main `.db` file whose `-wal` contains uncheckpointed changes. Rehearse against a staging MySQL database, back up the destination, inspect the dry-run, then apply only with an explicit confirmation:

```powershell
flask --app wsgi import-sqlite --source "D:\approved\retail-genie.sqlite"
flask --app wsgi import-sqlite --source "D:\approved\retail-genie.sqlite" --apply --confirm-apply
```

Applying is restricted to MySQL/MariaDB by the CLI. The importer is insert-only and transactional: identical existing IDs are skipped, a conflicting row aborts and rolls back the complete import, and it never overwrites target rows. Legacy JSON fields are mapped to JSON columns; money columns use `DECIMAL` with three fractional digits for OMR, percentage fields retain higher precision, and legacy datetimes are normalized to UTC. It preserves stable IDs and foreign-key relationships, including the cyclic order/demand-notice link. File-path values are retained, but uploaded files are **not** copied by this importer and must be reconciled/migrated separately.

All imported legacy passwords are reset to unknown random values and stored as Argon2 hashes by default; accounts are marked to require a password change. After approving an account, an operator can set a temporary password interactively on the server:

```powershell
flask --app wsgi reset-imported-password --username approved.admin
```

The user must replace that temporary password after signing in. For a vetted production source only, `--password-policy hash --confirm-legacy-passwords` explicitly retains legacy passwords as Argon2 hashes while still requiring a change at next sign-in. Do not apply the checked-in demo database to production. No password or password hash is printed by the import command.

For an approved data migration, run `db upgrade` first, then import before creating an initial admin if possible. The default reset policy imports legacy administrators with unknown passwords; use `reset-imported-password` for the approved admin account. If you create a separate admin before importing, choose a username not already present in the source so the unique username constraint cannot cause a conflict.

## Run tests

```powershell
python -m pytest
```

Tests use an isolated in-memory SQLite database and do not modify the sample database in `Node Js Version/`. MySQL DDL can be compiled offline, but no live office MySQL connection, real backup restore, or production import has been verified in this workspace.

## Security and deployment notes

- Login uses Argon2id password hashes, Flask-Login, CSRF-protected forms, signed `HttpOnly`/`Secure`/`SameSite` cookies, generic login errors, and rate limiting. The cookie contains only the user ID, a session freshness marker, and an authentication-version value; permissions and account status are reloaded from MySQL on requests. Incrementing the account's authentication version revokes older sessions.
- For the office rollout, put one always-on application server on the private LAN; give it a reserved LAN address; keep MySQL bound to the server and firewall port 3306 from client devices; expose the app only through HTTPS; set `SESSION_COOKIE_SECURE=true` and `FLASK_DEBUG=false`; keep uploads/backups on persistent server storage. Every workstation must use the same app URL, not its own local database.
- The office server OS is not confirmed yet, so the production WSGI/WebSocket server and TLS reverse-proxy instructions remain to be selected and tested for that OS. `python run.py` is local development only and must not be used as the exposed office production server.
- Admins create accounts from **Accounts**. There is no public registration. Managers with `manage_users` may create non-admin accounts, and cannot grant permissions they do not hold. Only the `admin` role can view or change backup settings.
- Do not commit `.env`, database backups, uploaded files, or production credentials. Back up the MySQL database and `UPLOADS_DIR` separately.
- In production, use HTTPS, set `SESSION_COOKIE_SECURE=true`, restrict the office firewall, and configure a shared rate-limit store if running multiple workers. Select and test the production WSGI/WebSocket server after the office server OS is confirmed. `python run.py` is for local development only.
- Socket.IO is wired into the app factory for the later real-time phase; no inventory/sales events are emitted yet.
- Apply schema changes with Alembic/Flask-Migrate and review every migration before it is run against production.
