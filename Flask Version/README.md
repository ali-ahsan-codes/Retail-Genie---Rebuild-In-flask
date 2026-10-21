# Retail Genie — Flask Version

This directory is the **Node-free Flask rebuild**. Phase 0–3 business workflows, **Phase 4 realtime/offline sync**, and **Phase 5 UI parity implementation** have passed local verification. The app's intended runtime/configuration remains MySQL. Phase 6 local readiness work is in progress; a read-only MySQL preflight is available, while live MySQL/staging reconciliation, real backup/restore, approved real-media migration, true MySQL concurrency, and the two-browser office-network test remain pending and are not implied by local test success. See [`PHASE_6_ACCEPTANCE.md`](PHASE_6_ACCEPTANCE.md), [`PHASE_0_WORKFLOW_INVENTORY.md`](PHASE_0_WORKFLOW_INVENTORY.md), [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md), [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md), and [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md). `Node Js Version/` remains the unchanged behavior reference.

The application does not use Node.js, npm, React, or a frontend build step. Flask serves the HTML templates and static CSS. The browser never connects directly to MySQL.

**Database policy:** MySQL 8/InnoDB remains the intended application database. Keep `DATABASE_URL` pointed to MySQL for actual app runs. SQLite is used only as an isolated test/migration-verification database; it is not a fallback production runtime or a substitute for the user's pending MySQL checks.

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

Administrators can open **Database backups** at `/admin/backups/` and set an interval (15 minutes to 7 days), retention count (1–365 files), enable/disable the schedule, and queue a one-time run. The defaults are disabled, daily, and 14 files. The app writes private, gzip-compressed `.sql.gz` dumps to `Flask Version/backup/` by default (override with `BACKUP_DIR`). A SHA-256 checksum, file size, run status, and sanitized error are recorded in MySQL. Before publishing a dump, the worker fully reads the gzip stream to validate its checksum and rejects empty or corrupt output. Older successful files are removed according to the configured retention count; audit rows remain. The app does not provide a public backup download URL.

Run **one separate scheduler/worker process** on the Flask/MySQL host; do not start a scheduler in each WSGI web worker:

```powershell
# Foreground worker (keeps checking the MySQL schedule)
flask --app wsgi backup-scheduler

# One check, useful for deployment/smoke tests
flask --app wsgi backup-scheduler --once
```

The worker uses a MySQL advisory lock to refuse a second scheduler for the same database. Configure the OS service manager to restart the worker after a host restart; the office server OS has not been confirmed, so a production service definition is not supplied yet. The one-time “Queue backup now” button also requires this worker to be running. Install `mysqldump` on the app host, set `MYSQLDUMP_PATH` if it is not on `PATH`, and size `BACKUP_TIMEOUT_SECONDS` for the database. Credentials are passed through a short-lived, permission-restricted MySQL option file, not command-line arguments. On Windows, protect the backup folder with an account-specific filesystem ACL.

The backup directory is intentionally outside Flask's static directory, is ignored by Git, and is created with owner-only permissions on POSIX hosts. Keep it on persistent storage and arrange a separate encrypted/off-host copy for disaster recovery; a backup on the same server is not protection against disk loss. Test restores before production use.

## Phase 3 implementation and local verification

Phase 3 business workflows are implemented locally across the catalog, sales, commercial, SCM, attendance, stock-audit, messaging, cloud-file, reports, display, and admin/settings modules. Highlights include scoped category/barcode/label workflows; transactional inventory ledger, imports/transfers/receiving; POS, open bills, exchange/store-credit, tax/discount, refund/cashup, fulfillment, and print views; commercial deposits, partial fulfillment, editing, conversion, print and opt-in SMTP email; supplier/PO attachments and logistics; attendance/breaks, evidence access, private messages/files, sales/activity reports, and privacy-limited LCD output. Role, tenant, store, and domain-policy checks plus audit history are retained.

Phase 3 closed with **135 passing tests**; Phase 5 closed with **145**, and the current Phase 6 local suite passes **146 tests**, with the opt-in MySQL test skipped until a test URL is configured. Isolated SQLite migration/schema upgrade/check/downgrade/re-upgrade also pass with no model drift. These checks are not live MySQL, staging, production-data, backup/restore, concurrency, or real-media acceptance. Configure `SMTP_HOST`, `SMTP_SENDER`, and the remaining `SMTP_*` settings to enable commercial email; sending fails closed when SMTP is not configured.

## Phase 4 realtime/offline implementation and local verification

A generalized MySQL-backed realtime outbox now emits scoped inventory, sales, payment, return, cashup, receiving, and access-change events in the transaction that changes the business record. Authenticated Socket.IO subscriptions recheck current tenant/domain/role/company/store authorization. Each app worker polls the shared outbox and emits only to its own local sockets; clients replay by event cursor after reconnect, including sales and inventory events. Retention preserves per-scope cursor floors and returns an explicit expired-cursor response. The sales pages display a refresh notice when another session changes store data.

Products & Inventory supports a browser IndexedDB queue for stock adjustments only. Retries use actor-scoped idempotency keys, so a lost response does not apply the same delta twice; mismatched retries and access changes are blocked and surfaced. Financial checkout/payment are deliberately not queued offline. See `MIGRATION_PLAN.md` for Phase 4 coverage and pending live-MySQL concurrency acceptance.

The current full local suite passes **146 tests**; the opt-in MySQL preflight test is skipped because no MySQL test URL is configured. Offline MySQL migration SQL generation succeeds (168,839 characters), while fresh SQLite migration/check/downgrade/re-upgrade passes. No live MySQL server is available here, so this is not live MySQL or staging verification.

## Phase 5 UI parity

The shared Flask shell now uses a responsive collapsible navigation, permission-filtered module links, and role-aware dashboard shortcuts. Existing module pages use the same Jinja/CSS foundation. POS and Express checkout accept keyboard-wedge barcode/SKU scans; label printing retains Code 39 output for supported values. Customer receipts are bilingual English/Arabic, OMR values keep three decimals, thermal receipts use an 80 mm print layout, and return/commercial documents include bilingual field labels. Express checkout exposes a print-last-receipt action, and the LCD order display remains a read-only, auto-refreshing surface. The Node app remains unchanged as a reference.

Phase 5 local implementation and automated checks pass; real device/printer/browser matrix and production workflow acceptance remain external gates. Phase 6 readiness work is in progress. The read-only `flask --app wsgi phase6-preflight` command is documented in `PHASE_6_ACCEPTANCE.md`; it must be run against approved staging MySQL before pilot acceptance.

## Phase 2 SQLite-to-MySQL import

The checked-in `Node Js Version/netpos.db` is confirmed **demo/sample data**, not the production dataset. The command below is a read-only dry run and is safe to use against that sample:

```powershell
flask --app wsgi import-sqlite --source "..\Node Js Version\netpos.db"
```

The importer requires the reviewed 27-table schema documented in `LEGACY_SCHEMA_MAP.md`, validates JSON, numeric precision, timestamps, usernames, permissions, and SQLite foreign keys, and reports table counts plus OMR order/payment, stock, and invoice-counter reconciliation totals. On apply, it verifies target row counts and foreign keys and aborts the transaction if those totals do not match. Legacy product rows are additionally seeded into the normalized catalog with a store-level opening balance and opening movement; repeated imports never overwrite live catalog edits or stock changes. The original landing rows remain available for reconciliation. It opens the source read-only and immutable; it never writes to the SQLite file. For any real migration, first make a verified, consistent SQLite backup. Close/checkpoint the source so committed WAL contents are included; do not point the importer at a live database or at a main `.db` file whose `-wal` contains uncheckpointed changes. Rehearse against a staging MySQL database, back up the destination, inspect the dry-run, then apply only with an explicit confirmation:

```powershell
flask --app wsgi import-sqlite --source "D:\approved\retail-genie.sqlite"
flask --app wsgi import-sqlite --source "D:\approved\retail-genie.sqlite" --apply --confirm-apply
```

Applying is restricted to MySQL/MariaDB by the CLI. The importer is insert-only and transactional: identical existing IDs are skipped, a conflicting row aborts and rolls back the complete import, and it never overwrites target rows. Legacy JSON fields are mapped to JSON columns; money columns use `DECIMAL` with three fractional digits for OMR, percentage fields retain higher precision, and legacy datetimes are normalized to UTC. It preserves stable IDs and foreign-key relationships, including the cyclic order/demand-notice link. The importer retains file-path metadata but does not copy uploaded files; migrate and verify those separately as described below.

### Legacy media migration

After the database import, run a read-only preflight against the same closed/checkpointed SQLite snapshot and its matching legacy `uploads/` directory:

```powershell
flask --app wsgi migrate-media --source "D:\approved\retail-genie.sqlite" --source-uploads "D:\approved\uploads"
```

Review the counts and resolve any missing files before applying. Applying requires the imported target company and an explicit confirmation:

```powershell
flask --app wsgi migrate-media --source "D:\approved\retail-genie.sqlite" --source-uploads "D:\approved\uploads" --company-id "approved-company-id" --apply --confirm-apply
```

The utility rejects unsafe paths and symbolic links, checks source-file hashes, refuses to overwrite different destination content, copies the complete uploads tree (including orphaned files) into private `UPLOADS_DIR` storage under a deterministic tenant/company namespace, updates only matching imported rows in a database transaction, and verifies each local database path resolves to a file. Legacy per-user cloud manifests are validated and rewritten to scoped file URLs; cloud-owner directories without a matching source account are reported for review. The operation is idempotent and leaves the SQLite source untouched. External URLs and embedded image data are preserved but reported separately; they are not copied. Set `UPLOADS_DIR` to persistent private storage (default: `Flask Version/uploads`). The CLI does not expose uploaded files publicly. The checked-in sample database contains no referenced local upload files, and this checkout has no production uploads directory; real media migration still requires the approved source media and staging MySQL sign-off.

All imported legacy passwords are reset to unknown random values and stored as Argon2 hashes by default; accounts are marked to require a password change. After approving an account, an operator can set a temporary password interactively on the server:

```powershell
flask --app wsgi reset-imported-password --username approved.admin
```

The user must replace that temporary password after signing in. For a vetted production source only, `--password-policy hash --confirm-legacy-passwords` explicitly retains legacy passwords as Argon2 hashes while still requiring a change at next sign-in. Do not apply the checked-in demo database to production. No password or password hash is printed by the import command.

For an approved data migration, run `db upgrade` first, then import before creating an initial admin if possible. The default reset policy imports legacy administrators with unknown passwords; use `reset-imported-password` for the approved admin account. If you create a separate admin before importing, choose a username not already present in the source so the unique username constraint cannot cause a conflict.

## SaaS tenant-container status

The tenant-container architecture is documented in [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md), with current status and build order in [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md). The confirmed design is one shared MySQL database, one logical container per independent customer, and child companies/branches inside that tenant. Phase 0–5 local implementation checks have passed; live MySQL/staging/restore/media and concurrent-session acceptance are deferred to an available MySQL environment. Phase 6 readiness is in progress; pilot/cutover has not started. Company-level sharing remains the conservative default, and only Main Admin can change policies. The Phase 0 choices and outstanding external gates are recorded in the inventory and migration plan.

## Run tests

```powershell
python -m pytest
```

The suite currently passes **146 tests**; one opt-in MySQL test is skipped until a disposable MySQL test URL is configured. Tests use isolated SQLite databases and do not modify the sample database in `Node Js Version/`. A fresh SQLite Alembic upgrade and schema check, downgrade, and re-upgrade pass with no model drift. Offline MySQL DDL generation succeeds, but these are local checks only: no live office MySQL connection, staging reconciliation, true MySQL concurrency, real backup restore, production import, or real-media migration has been verified in this workspace.

## Security and deployment notes

- Login uses Argon2id password hashes, Flask-Login, CSRF-protected forms, signed `HttpOnly`/`Secure`/`SameSite` cookies, generic login errors, and rate limiting. The cookie contains only the user ID, a session freshness marker, and an authentication-version value; permissions and account status are reloaded from MySQL on requests. Incrementing the account's authentication version revokes older sessions.
- For the office rollout, put one always-on application server on the private LAN; give it a reserved LAN address; keep MySQL bound to the server and firewall port 3306 from client devices; expose the app only through HTTPS; set `SESSION_COOKIE_SECURE=true` and `FLASK_DEBUG=false`; keep uploads/backups on persistent server storage. Every workstation must use the same app URL, not its own local database.
- The office server OS is not confirmed yet, so the production WSGI/WebSocket server and TLS reverse-proxy instructions remain to be selected and tested for that OS. `python run.py` is local development only and must not be used as the exposed office production server.
- Admins create accounts from **Accounts**. There is no public registration. Managers with `manage_users` may create non-admin accounts, and cannot grant permissions they do not hold. Only the `admin` role can view or change backup settings.
- Do not commit `.env`, database backups, uploaded files, or production credentials. Back up the MySQL database and `UPLOADS_DIR` separately.
- In production, use HTTPS, set `SESSION_COOKIE_SECURE=true`, restrict the office firewall, and configure a shared rate-limit store if running multiple workers. Select and test the production WSGI/WebSocket server after the office server OS is confirmed. `python run.py` is for local development only.
- Phase 4 uses durable DB outbox events and per-worker polling for Socket.IO fanout; Redis is not required for this implementation. The browser reconnects/replays authorized events and exposes a refresh notice on sales pages. Stock adjustments alone may be queued offline; financial operations remain online-only. No Node/npm runtime or frontend build is required.
- Apply schema changes with Alembic/Flask-Migrate and review every migration before it is run against production.
