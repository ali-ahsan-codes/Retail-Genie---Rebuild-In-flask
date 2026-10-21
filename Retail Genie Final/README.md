# Retail Genie Final

A clean, standalone copy of the Flask + MySQL Retail Genie application source, database migrations, tests, and local installation guide. It excludes the legacy Node app, phase-planning documents, databases, uploads, backups, caches, and virtual environments.

## Start here

- **Install MySQL and Retail Genie locally:** [`LOCAL_INSTALL_GUIDE.md`](LOCAL_INSTALL_GUIDE.md)
- **Configuration example:** copy `.env.example` to `.env` and set a strong `SECRET_KEY` and local MySQL `DATABASE_URL`.
- **Database schema:** `flask --app wsgi db upgrade`
- **Create the first administrator:** `flask --app wsgi create-admin --username admin`
- **Run locally:** `python run.py`
- **Run the tests:** `python -m pytest`

The app's target database is MySQL 8/InnoDB. SQLite is used only for isolated automated tests; it is not a production fallback. The optional live-MySQL integration test requires a separate disposable test database. Do not expose MySQL port 3306 to client devices.

## Included files

- `retail_genie/` — Flask application, templates, CSS/JS assets, and static vendor assets.
- `migrations/` — Alembic schema history.
- `tests/` — automated unit, route, tenant-isolation, and regression tests.
- `requirements.txt`, `run.py`, `wsgi.py`, `pytest.ini`, `.env.example`, `.gitignore`.
- `LOCAL_INSTALL_GUIDE.md` — step-by-step local MySQL/Workbench installation, LAN QR access, and first-run setup.
- `testing/dashboard-desktop-test.png` — desktop dashboard test capture from the temporary UI preview.

## Verification record

The included source was run through the complete local suite: **158 passed, 1 skipped**. The skipped test requires an explicitly configured disposable MySQL integration database. The Alembic chain was also upgraded, schema-checked, downgraded to the previous revision, and re-upgraded using a temporary SQLite database; offline MySQL DDL generation is not a live MySQL test.

The screenshot is a UI test capture using temporary demo data. Its QR graphic contains this sandbox's temporary preview URL and is illustrative only; a real installation generates a fresh login QR for its current LAN/public URL. No production customer data, passwords, `.env` file, live MySQL database, uploads, or backups are included. MySQL staging, backup/restore, office-network, concurrency, and production deployment acceptance remain separate checks.
