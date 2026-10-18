# Retail Genie — Flask Version

This directory is the **Node-free Flask rebuild**. Phase 0 and the local Phase 1 foundation are complete; Phase 2 has passed SQLite-backed local verification, and **Phase 3 is active but incomplete**. Per the user's updated direction, isolated SQLite tests/checks may be used without waiting for attached MySQL; the app's intended runtime/configuration remains MySQL. The user will verify MySQL locally later. Live MySQL/staging reconciliation, real backup/restore, approved real-media migration, and the two-browser office-network test remain pending and are not implied by local test success. Phase 4 remains paused until Phase 3 acceptance. See [`PHASE_0_WORKFLOW_INVENTORY.md`](PHASE_0_WORKFLOW_INVENTORY.md), [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md), [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md), and [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md). `Node Js Version/` remains the unchanged behavior reference.

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

## Current Phase 3 catalog and sales slice (unfinished)

`/catalog/products` provides tenant/policy-scoped product and inventory search, including SKU, category, and barcode lookup (USB barcode scanners can enter a code in the search field). Authorized users can import/export CSV: imports are limited to 2 MB/1000 rows, match updates by SKU only within the selected company, roll back as one transaction on any invalid row, and apply stock quantities only with the required inventory permissions. Exports omit stock and threshold values when the account cannot view inventory. Store transfers are limited to accessible stores within one legal company and update both balances with paired ledger entries, audit history, and per-store events in one transaction.

The sales slice also has a manager/admin-only settled-order return/refund screen and API. Each return requires an idempotency key, is limited to unreturned line quantities and the amount paid, restores catalog stock with audit/realtime history, and reduces the applicable tender's daily cashup total. Initial demand-notice and quotation workflows include company-scoped numbering, audit/status controls, and conversion of eligible catalog-linked documents into stock-backed open bills while preserving quote prices. Deposits, partial fulfillment, quote printing/email, exchanges/store credit, tax/discount handling and return-slip printing remain open. This is still not Phase 3 acceptance: purchasing/receiving, attendance/audits, messaging/files/reports, category management, barcode/label printing, the LCD display, and other legacy workflows remain. Phase 4 remains paused until Phase 3 is explicitly completed and accepted.

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

The tenant-container architecture is documented in [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md), with current status and build order in [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md). The confirmed design is one shared MySQL database, one logical container per independent customer, and child companies/branches inside that tenant. Phase 0 and local Phase 1 are closed; Phase 2's isolated SQLite implementation checks have passed, with live MySQL/staging/restore/media acceptance deferred to the user's local MySQL environment and Phase 6. Phase 3 is active but incomplete; Phase 4 remains paused. Company-level sharing remains the conservative default, and only Main Admin can change policies. The Phase 0 choices and outstanding external gates are recorded in the inventory and migration plan.

## Run tests

```powershell
python -m pytest
```

The suite currently passes 114 tests (36 Phase 2-focused tests; 52 selected Phase 3 sales/catalog/tenancy/commercial tests). Tests use an isolated in-memory SQLite database and do not modify the sample database in `Node Js Version/`. A fresh SQLite Alembic upgrade and `flask db check` pass, and MySQL DDL can be generated offline. These results are local checks only: no live office MySQL connection, staging reconciliation, real backup restore, production import, or real-media migration has been verified in this workspace. The user plans to run the MySQL acceptance checks locally.

## Security and deployment notes

- Login uses Argon2id password hashes, Flask-Login, CSRF-protected forms, signed `HttpOnly`/`Secure`/`SameSite` cookies, generic login errors, and rate limiting. The cookie contains only the user ID, a session freshness marker, and an authentication-version value; permissions and account status are reloaded from MySQL on requests. Incrementing the account's authentication version revokes older sessions.
- For the office rollout, put one always-on application server on the private LAN; give it a reserved LAN address; keep MySQL bound to the server and firewall port 3306 from client devices; expose the app only through HTTPS; set `SESSION_COOKIE_SECURE=true` and `FLASK_DEBUG=false`; keep uploads/backups on persistent server storage. Every workstation must use the same app URL, not its own local database.
- The office server OS is not confirmed yet, so the production WSGI/WebSocket server and TLS reverse-proxy instructions remain to be selected and tested for that OS. `python run.py` is local development only and must not be used as the exposed office production server.
- Admins create accounts from **Accounts**. There is no public registration. Managers with `manage_users` may create non-admin accounts, and cannot grant permissions they do not hold. Only the `admin` role can view or change backup settings.
- Do not commit `.env`, database backups, uploaded files, or production credentials. Back up the MySQL database and `UPLOADS_DIR` separately.
- In production, use HTTPS, set `SESSION_COOKIE_SECURE=true`, restrict the office firewall, and configure a shared rate-limit store if running multiple workers. Select and test the production WSGI/WebSocket server after the office server OS is confirmed. `python run.py` is for local development only.
- A partial Products & Inventory realtime slice remains in the working tree from earlier out-of-order work: it uses a locally vendored Socket.IO browser client and a cursor replay API, but is paused and not phase-accepted. No Node/npm runtime or frontend build is required; the broader Phase 4 work still awaits its turn in the phase gate sequence.
- Apply schema changes with Alembic/Flask-Migrate and review every migration before it is run against production.
