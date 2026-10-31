# Retail Genie Final

Retail Genie is a standalone Flask application for retail operations, backed by MySQL. This folder contains the application source, runtime dependencies, a MySQL schema for a new installation, and a local setup guide.

## Start here

- **Company, role, inventory, and container guide (standalone HTML):** [`COMPANY_CONTAINER_GUIDE.html`](COMPANY_CONTAINER_GUIDE.html). Open it in a browser; its screenshot assets are in `preview/`.
- **Install and configure the app:** [`LOCAL_INSTALL_GUIDE.md`](LOCAL_INSTALL_GUIDE.md)

The in-app HTML guide is also available at `/admin/company-container-guide` to authorized Company Admin and Main Admin users. Its Jinja template is `retail_genie/templates/admin/company_container_guide.html`; the standalone HTML above is easier to locate and open outside the app.
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

The 2026 interface refresh applies the forest-glass header, mineral canvas, citron highlights, animated ambient gradients, and responsive component system across module pages (accounts, catalog, attendance, sales/POS, SCM, audits, messaging, reports, SaaS, and settings). The standalone live-order display now follows the same visual language, and print views use clean paper styling. Motion respects the operating-system reduced-motion preference. Screenshots were recaptured from an isolated browser preview using synthetic demo records; they are illustrative only and do **not** represent live-MySQL validation.

- [Dashboard — desktop](preview/dashboard.png) · [mobile](preview/dashboard-mobile.png)
- [Sign-in — desktop](preview/login-desktop.png) · [mobile](preview/login-mobile.png)
- [Products & inventory — desktop](preview/products-inventory.png) · [mobile](preview/products-mobile.png)
- [Point of sale — initial view](preview/point-of-sale.png) · [open demo bill](preview/pos-demo-open-bill.png) · [settled demo invoice](preview/pos-demo-settled-invoice.png)
- [Supply chain](preview/supply-chain.png)
- [Stock audits](preview/stock-audits.png)
- [Settings](preview/settings.png)
- [Accounts](preview/accounts.png)
- [Role-by-role dashboards and navigation (all 11 account types)](preview/account-roles/README.md)
- [Latest role-based verification, link checks, and screenshots](preview/role-verification/README.md)
- [Full-app module previews](preview/full-app/README.md)

The directory is intended to be copied or deployed as an independent application. Local credentials, environment files, database data, uploads, and backups are not included.
