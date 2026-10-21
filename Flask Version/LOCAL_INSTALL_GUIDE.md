# Retail Genie local installation guide

This guide installs the Flask app and MySQL on a Windows PC for local development or a same-private-Wi-Fi trial. It also explains how to let phones/tablets scan a QR code to open the current login URL. The Flask development server is **not approved for production use**; the live office WSGI/TLS deployment remains a separate Phase 6 gate.

## 1. Install prerequisites

Install these on the PC that will run Retail Genie:

1. **Python 3.11 or newer**. In PowerShell, verify with `py -3.11 --version`.
2. **MySQL Community Server 8.x** (InnoDB) and optionally MySQL Workbench. On Windows, use the MySQL Community Installer and configure the local server service (commonly `MySQL80`) with a strong root password. Keep MySQL bound to the PC; other devices use the Flask app and must not connect directly to MySQL.
3. **Git** if you are cloning the repository, and a modern browser.

In PowerShell, confirm that the MySQL service is running:

```powershell
Get-Service MySQL80
# If it is stopped, run PowerShell as Administrator and:
Start-Service MySQL80
```

If the service has a different name, find it with `Get-Service *mysql*`.

## 2. Create the MySQL database and restricted app account

Use MySQL Workbench to connect to the local MySQL server, open a SQL tab, paste the statements below, replace the sample password, and execute them. You can also run the same SQL in the MySQL command-line client.

```sql
CREATE DATABASE retail_genie
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER 'retail_genie'@'127.0.0.1'
  IDENTIFIED BY 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';

GRANT ALL PRIVILEGES ON retail_genie.*
  TO 'retail_genie'@'127.0.0.1';

FLUSH PRIVILEGES;
```

The application connects over TCP to `127.0.0.1:3306`, so the SQL account host is also `127.0.0.1`. The grant is limited to the `retail_genie` schema; do not use the MySQL root account in the app URL. Do not open MySQL port 3306 to phones, tablets, or the public internet.

Optional connection check from PowerShell:

```powershell
Test-NetConnection 127.0.0.1 -Port 3306
```

## 3. Create the Python environment and install the app

Open PowerShell in the repository and run:

```powershell
cd "Flask Version"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks virtual-environment activation, either allow scripts for your user with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or skip activation and call `.venv\Scripts\python.exe` and `.venv\Scripts\flask.exe` directly.

## 4. Configure `.env`

Open `Flask Version/.env` in a text editor. Set a newly generated secret key in the `SECRET_KEY` line. Generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the database URL to the database and app account created above:

```dotenv
DATABASE_URL=mysql+pymysql://retail_genie:URL_ENCODED_PASSWORD@127.0.0.1:3306/retail_genie?charset=utf8mb4
```

Replace `URL_ENCODED_PASSWORD` with the app account password. URL-encode reserved characters such as `@`, `:`, `/`, `#`, and `%`; alternatively, use a strong generated password whose characters need no URL escaping. Do not paste the MySQL root password here.

For a **single-PC local setup**, keep:

```dotenv
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=false
SESSION_COOKIE_SECURE=false
PUBLIC_BASE_URL=
```

`SESSION_COOKIE_SECURE=false` is only for local HTTP development. Never use that setting for a production HTTPS deployment. Leave `PUBLIC_BASE_URL` blank for LAN-IP detection; if the app is behind a reverse proxy or uses a fixed DNS name, set it to the externally reachable base URL, for example `https://retail.example.com`.

## 5. Create the schema and first administrator

From `Flask Version/` with the virtual environment active:

```powershell
flask --app wsgi db upgrade
flask --app wsgi create-admin --username admin
```

The create-admin command prompts for and confirms a password. There is no default login. Use a unique password of at least 12 characters. The Main Admin can then create customer/tenant companies and user accounts from the app; public self-registration is disabled.

Start the local app:

```powershell
python run.py
```

Keep this PowerShell window open while using the app. Visit `http://127.0.0.1:5000/` on the server PC. Check `/healthz` for process health and `/readyz` for database readiness. The login page should appear; sign in with the administrator credentials you just created.

## 6. Let users scan a QR code on the same Wi-Fi network

The QR code is rendered only on **desktop/laptop and tablet user agents**. Phone user agents do not receive the QR panel or QR image request.

To share the app with phones/tablets on the same trusted private Wi-Fi:

1. Connect the server PC and client devices to the same non-guest Wi-Fi/LAN. Guest networks often block device-to-device traffic.
2. In `.env`, change the local runner bind address to:

   ```dotenv
   FLASK_HOST=0.0.0.0
   FLASK_PORT=5000
   FLASK_DEBUG=false
   ```

3. Allow inbound TCP port 5000 **only on the Windows Private network profile**. Run PowerShell as Administrator:

   ```powershell
   New-NetFirewallRule -DisplayName "Retail Genie local LAN" `
     -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000 -Profile Private
   ```

   Do not create a public-profile rule, and do not open MySQL port 3306.
4. Stop and restart `python run.py` so it picks up the new `.env` setting.
5. On the server PC, open `http://127.0.0.1:5000/login`. Select **Open on phone** in the header. The QR encodes the server's current LAN IPv4 address and login path. Scan it with the phone/tablet camera; the device opens the Retail Genie login page.
6. The phone/tablet must remain on the same Wi-Fi/LAN. Sign in using an account created by the Main Admin.

The QR is generated from the active network route each time the page/image is requested; it is not a permanent printed address. If the PC gets a different IP after a daily DHCP change, reopen the local login page on the server PC and scan the refreshed QR. Old QR printouts may be stale. If the PC has several network adapters and the QR chooses the wrong address, run `ipconfig`, identify the Wi-Fi/Ethernet IPv4 address reachable by clients, and set `PUBLIC_BASE_URL=http://<that-ip>:5000` in `.env`; restart the app. For example, use the actual address in place of `<that-ip>`.

If your server is behind a reverse proxy or a stable DNS name, set `PUBLIC_BASE_URL` to the full external base URL (including `https://` where configured). The QR points to that base plus `/login`.

## 7. Add tenant companies and users

1. Sign in as the Main Admin created during installation.
2. Use **Companies** to provision a tenant company, its first store, and Company Admin. The Company Admin receives a forced password change at first sign-in.
3. Use **Accounts** to create additional user accounts. Assign their roles and permissions, then use **Store access** to grant only the required stores.
4. Keep every customer in its own tenant container. Do not create separate MySQL databases per tenant; the SaaS model uses one MySQL database with server-enforced tenant isolation.
5. If using Phase 7 subscription plans, create plans and explicitly assign subscriptions in **SaaS plans** / **Tenant subscriptions**. Existing tenants without an assigned plan remain unmetered; no customer is silently billed.

## 8. Routine start/stop and basic troubleshooting

- Start: open PowerShell, `cd "Flask Version"`, activate `.venv`, then run `python run.py`.
- Stop: press `Ctrl+C` in the runner window. MySQL remains a separate Windows service.
- If login opens but database readiness fails, check `Get-Service MySQL80`, the `DATABASE_URL`, MySQL account host/grant, and port 3306 locally.
- If another device cannot connect, verify both devices are on the same private Wi-Fi, `FLASK_HOST=0.0.0.0`, the PC's Private firewall rule allows TCP 5000, and that the displayed QR is current. Never solve this by exposing port 3306.
- If `flask` is not found, activate `.venv` or run `\.venv\Scripts\flask.exe --app wsgi ...` from `Flask Version/`.
- Run the local regression suite with `python -m pytest`. The optional MySQL integration test requires a separate disposable MySQL test database.

## Important production boundary

`python run.py` is for local development and a controlled same-LAN trial only. Do not expose Flask's development server directly to the internet or treat this guide as production acceptance. Production requires an approved WSGI/WebSocket server, HTTPS/TLS reverse proxy, persistent storage, private MySQL access, tested backups/restores, live MySQL migration and concurrency checks, and the remaining Phase 6 approval gates. The SQLite test database and offline MySQL DDL are not substitutes for live MySQL validation.
