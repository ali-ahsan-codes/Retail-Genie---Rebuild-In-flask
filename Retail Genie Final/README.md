# Retail Genie Final

Retail Genie is a standalone Flask application for retail operations, backed by MySQL. This folder contains the application source, runtime dependencies, a MySQL schema for a new installation, and a local setup guide.

## Start here

- **Install and configure the app:** [`LOCAL_INSTALL_GUIDE.md`](LOCAL_INSTALL_GUIDE.md)
- **Understand app architecture and functions:** [`APPLICATION_BLUEPRINT.md`](APPLICATION_BLUEPRINT.md)
- **Configure a fresh local install:** run `install.ps1`; it creates the isolated `.env.retail-genie` settings file and provisions the new `retail_genie` database. Do not copy credentials from an unrelated `.env`.
- **Initial database structure:** [`database-schema.sql`](database-schema.sql) is for a new, empty `retail_genie` database; the installer applies it during setup.
- **Create the first administrator:** `python seed_admin.py` prompts for a new Main Admin account.
- **Optional local demo records:** `python -m flask --app wsgi seed-demo --confirm-demo-data` (fresh local `retail_genie` database only; see the install guide).
- **Run locally:** `python run.py`

The target database is MySQL 8.0.16 or newer with InnoDB. The supplied schema is for a fresh installation only; do not execute it against a database containing existing business data. Never expose MySQL port 3306 to client devices or the internet. Retail Genie uses its separate `retail_genie` database and does not modify the existing `invoiceflow_v2` database.

## Application contents

- `retail_genie/` — Flask application, templates, styles, scripts, and static assets.
- `database-schema.sql` — initial MySQL tables and indexes for a fresh database.
- `requirements.txt` — application runtime dependencies.
- `run.py`, `wsgi.py`, `.env.example`, `.gitignore` — application entry points and configuration support.
- `install.ps1`, `scripts/setup_database.py`, `seed_admin.py` — local setup, database provisioning, and interactive administrator creation.
- `LOCAL_INSTALL_GUIDE.md` — Windows/MySQL setup, LAN QR access, and initial account configuration.

## UI previews

These screenshots were captured from an isolated local browser preview using synthetic demo records. They are illustrative only and do **not** represent live-MySQL validation.

- [Dashboard](preview/dashboard.png)
- [Sign-in — desktop](preview/login-desktop.png) · [mobile](preview/login-mobile.png)
- [Products & inventory — desktop](preview/products-inventory.png) · [mobile](preview/products-mobile.png)
- [Point of sale — initial view](preview/point-of-sale.png) · [open demo bill](preview/pos-demo-open-bill.png) · [settled demo invoice](preview/pos-demo-settled-invoice.png)
- [Supply chain](preview/supply-chain.png)
- [Stock audits](preview/stock-audits.png)
- [Settings](preview/settings.png)
- [Accounts](preview/accounts.png)

The directory is intended to be copied or deployed as an independent application. Local credentials, environment files, database data, uploads, and backups are not included.
