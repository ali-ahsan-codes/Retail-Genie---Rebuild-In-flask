# Retail Genie — Flask Version

This directory is the **Node-free Flask rebuild**. Phase 1 now includes the Python application factory, environment-based MySQL configuration, secure account authentication, server-side role/permission checks, health endpoints, and tests. Sales, inventory, SCM, reports, real-time business events, and the remaining screens are not migrated yet; the existing Node version remains the reference while those phases are developed.

The application does not use Node.js, npm, React, or a frontend build step. Flask serves the HTML templates and static CSS. The browser never connects directly to MySQL.

## Requirements

- Python 3.11 or newer
- MySQL 8.x (InnoDB, `utf8mb4`)
- A long random Flask secret key

Create a MySQL database and a dedicated application user. Run these statements in MySQL, replacing the example password with a unique secret:

```sql
CREATE DATABASE retail_genie CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'retail_genie'@'localhost' IDENTIFIED BY 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';
GRANT ALL PRIVILEGES ON retail_genie.* TO 'retail_genie'@'localhost';
```

Keep MySQL bound to the office server; do not expose port 3306 to client devices or the public internet. Only the Flask server should connect to the database.

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

Then initialize the schema and create the first administrator interactively:

```powershell
flask --app wsgi db upgrade
flask --app wsgi create-admin --username admin
python run.py
```

The create-admin command prompts for a password and confirmation. There is no default/demo account or password. Use a unique password of at least 12 characters.

Open `http://127.0.0.1:5000/`. Health endpoints are available at `/healthz` and `/readyz` (the latter checks the MySQL connection).

## Run tests

```powershell
python -m pytest
```

Tests use an isolated in-memory SQLite database and do not touch the sample database in `Node Js Version/`. MySQL remains the required target for real application data; run an integration check against the office MySQL instance before deployment.

## Security and deployment notes

- Login uses Argon2id password hashes, Flask-Login, CSRF-protected forms, signed `HttpOnly`/`Secure`/`SameSite` cookies, generic login errors, and rate limiting. The cookie contains only the user ID, a session freshness marker, and an authentication-version value; permissions and account status are reloaded from MySQL on requests. Incrementing the account's authentication version revokes older sessions.
- For the office rollout, put one always-on application server on the private LAN; give it a reserved LAN address; keep MySQL bound to the server and firewall port 3306 from client devices; expose the app only through HTTPS; set `SESSION_COOKIE_SECURE=true` and `FLASK_DEBUG=false`; keep uploads/backups on persistent server storage. Every workstation must use the same app URL, not its own local database.
- The office server OS is not confirmed yet, so the production WSGI/WebSocket server and TLS reverse-proxy instructions remain to be selected and tested for that OS. `python run.py` is local development only and must not be used as the exposed office production server.
- Admins create accounts from **Accounts**. There is no public registration. Managers with `manage_users` may create non-admin accounts, and cannot grant permissions they do not hold.
- Do not commit `.env`, database backups, uploaded files, or production credentials. Back up the MySQL database and `UPLOADS_DIR` separately.
- In production, use HTTPS, set `SESSION_COOKIE_SECURE=true`, restrict the office firewall, and configure a shared rate-limit store if running multiple workers. Select and test the production WSGI/WebSocket server after the office server OS is confirmed. `python run.py` is for local development only.
- Socket.IO is wired into the app factory for the later real-time phase; no inventory/sales events are emitted yet.
- Apply schema changes with Alembic/Flask-Migrate and review every migration before it is run against production.
