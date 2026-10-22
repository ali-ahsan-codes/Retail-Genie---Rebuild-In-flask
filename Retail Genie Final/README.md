# Retail Genie Final

Retail Genie is a standalone Flask application for retail operations, backed by MySQL. This folder contains the application source, runtime dependencies, a MySQL schema for a new installation, and a local setup guide.

## Start here

- **Install and configure the app:** [`LOCAL_INSTALL_GUIDE.md`](LOCAL_INSTALL_GUIDE.md)
- **Understand app architecture and functions:** [`APPLICATION_BLUEPRINT.md`](APPLICATION_BLUEPRINT.md)
- **Configuration example:** copy `.env.example` to `.env`, set a strong `SECRET_KEY`, and configure the MySQL `DATABASE_URL`.
- **Initial database structure:** execute [`database-schema.sql`](database-schema.sql) against a new, empty `retail_genie` database.
- **Create the first administrator:** `flask --app wsgi create-admin --username admin`
- **Optional local demo records:** `flask --app wsgi seed-demo --confirm-demo-data` (fresh local `retail_genie` database only; see the install guide).
- **Run locally:** `python run.py`

The target database is MySQL 8.0.16 or newer with InnoDB. The supplied schema is for a fresh installation only; do not execute it against a database containing existing business data. Never expose MySQL port 3306 to client devices or the internet.

## Application contents

- `retail_genie/` — Flask application, templates, styles, scripts, and static assets.
- `database-schema.sql` — initial MySQL tables and indexes for a fresh database.
- `requirements.txt` — application runtime dependencies.
- `run.py`, `wsgi.py`, `.env.example`, `.gitignore` — application entry points and configuration support.
- `LOCAL_INSTALL_GUIDE.md` — Windows/MySQL Workbench setup, LAN QR access, and initial account configuration.
- `preview/dashboard.png` — illustrative dashboard screenshot from a temporary UI preview. Its QR graphic contains a temporary preview URL; an actual installation generates a fresh QR code for its current address.

The directory is intended to be copied or deployed as an independent application. Local credentials, environment files, database data, uploads, and backups are not included.
