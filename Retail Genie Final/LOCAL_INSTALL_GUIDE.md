# Retail Genie Final — Local installation

This guide installs Retail Genie on a Windows PC using MySQL Community Server and MySQL Workbench. It also describes same-Wi-Fi access for phones and tablets using the app's dynamically generated QR code.

## 1. Install the prerequisites

On the PC that will run Retail Genie, install:

- Python 3.11 or newer
- MySQL Community Server 8.0.16 or newer with InnoDB
- MySQL Workbench (recommended for database setup)
- Git, if cloning the repository

In PowerShell, confirm that the MySQL service is running:

```powershell
Get-Service *mysql*
```

If needed, start the MySQL service from Windows Services or from elevated PowerShell with `Start-Service MySQL80` (the service name can differ).

## 2. Create the database and application account

In MySQL Workbench, connect to your local server, open a SQL tab, replace the sample password, and execute:

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

The application connects to `127.0.0.1:3306`; the database account is limited to the `retail_genie` schema. Do not use the MySQL root account in the app configuration, and do not expose MySQL port 3306 to client devices or the internet.

## 3. Install the application

Open PowerShell at the repository location:

```powershell
cd "Retail Genie Final"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If activation is blocked by PowerShell policy, allow script activation for your user or invoke `.venv\Scripts\python.exe` and `.venv\Scripts\flask.exe` directly.

## 4. Configure `.env`

Generate a strong secret key:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put it in `.env` as `SECRET_KEY`. Set the database URL to the account and schema created above:

```dotenv
DATABASE_URL=mysql+pymysql://retail_genie:URL_ENCODED_PASSWORD@127.0.0.1:3306/retail_genie?charset=utf8mb4
```

Replace `URL_ENCODED_PASSWORD` with the application account password. URL-encode reserved characters such as `@`, `:`, `/`, `#`, and `%`. Do not use the MySQL root password.

For one-PC local use, these values are suitable:

```dotenv
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=false
SESSION_COOKIE_SECURE=false
PUBLIC_BASE_URL=
```

`SESSION_COOKIE_SECURE=false` is for local HTTP use only. For HTTPS hosting, use `SESSION_COOKIE_SECURE=true`. Leave `PUBLIC_BASE_URL` empty for LAN address detection. If the app is behind a reverse proxy or has a stable DNS name, set `PUBLIC_BASE_URL` to its reachable base address, such as `https://retail.example.com`.

## 5. Install the initial MySQL schema and create the Main Admin

The included `database-schema.sql` defines the empty application's MySQL tables and indexes. It is for a **new, empty `retail_genie` database only**.

In MySQL Workbench:

1. Open `database-schema.sql`.
2. Select the `retail_genie` schema as the active/default schema.
3. Execute the script and confirm it completes without errors.

Alternatively, from Command Prompt (`cmd.exe`) in the application folder, run this after installing the MySQL command-line client:

```cmd
mysql --host=127.0.0.1 --port=3306 --user=retail_genie --password retail_genie < database-schema.sql
```

The client prompts for the MySQL application account password. Do not execute the schema file on a database that contains customer data.

Create the first Main Admin:

```powershell
flask --app wsgi create-admin --username admin
```

The command prompts for and confirms a password. Use a unique password with at least 12 characters. There is no default account or password.

Optional: add sample company/store/products and opening inventory for a **fresh local development database only**:

```powershell
flask --app wsgi seed-demo --confirm-demo-data
```

This explicit command is restricted to a local MySQL database named `retail_genie`; it refuses to run if business records already exist. It adds one demo tenant, one company, one store, five sample products, and demo-only opening stock. It does not create a login account or sales/customer history. Skip it for a real installation.

## 6. Start Retail Genie

```powershell
python run.py
```

Keep the PowerShell window open. On the server PC, open `http://127.0.0.1:5000/`. The `/healthz` page reports app health; `/readyz` checks the MySQL connection. Sign in using the Main Admin account created above.

## 7. Share the login page with the QR code

The **Open on phone** QR panel appears for desktop, laptop, and tablet browsers. Phone browsers do not show the QR panel. The code points to the current login address; it is generated as the app is opened, so a daily LAN IP change does not require a hard-coded URL in the app.

For phones/tablets on the same trusted private Wi-Fi:

1. Connect the server PC and the client devices to the same non-guest Wi-Fi/LAN.
2. In `.env`, set:

   ```dotenv
   FLASK_HOST=0.0.0.0
   FLASK_PORT=5000
   FLASK_DEBUG=false
   ```

3. Allow inbound TCP port 5000 on the Windows **Private** network profile only. From PowerShell running as Administrator:

   ```powershell
   New-NetFirewallRule -DisplayName "Retail Genie local LAN" `
     -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000 -Profile Private
   ```

   Do not create a Public-profile rule or open port 3306.
4. Restart `python run.py`.
5. On the server PC, open `http://127.0.0.1:5000/login`, select **Open on phone**, and scan the QR with the phone/tablet camera.
6. Keep the phone/tablet on the same Wi-Fi/LAN and sign in with an account created by the Main Admin.

If the PC's address changes, reopen the local login page on the PC and scan the refreshed QR. If several network adapters are present and the detected address is not reachable by clients, use `ipconfig` to identify the correct Wi-Fi/Ethernet address and set `PUBLIC_BASE_URL=http://<current-lan-ip>:5000` in `.env`, then restart the app. For reverse-proxy or DNS hosting, set `PUBLIC_BASE_URL` to the full externally reachable base address, including HTTPS when configured.

## 8. Set up tenant users

1. Sign in as Main Admin.
2. Use **Companies** to add a tenant company, its first store, and its Company Admin.
3. Use **Accounts** to create staff accounts, assign roles/permissions, and grant only the required store access.
4. Each independent customer belongs in a separate logical tenant container within the shared MySQL database.
5. If using subscription plans, add a plan under **SaaS plans** and explicitly assign it under **Tenant subscriptions**. Existing tenants without a plan remain unmetered.

## Start/stop and troubleshooting

- Start: `cd "Retail Genie Final"`, activate `.venv`, then `python run.py`.
- Stop: press `Ctrl+C` in the runner window. MySQL runs as a separate Windows service.
- If `/readyz` is unavailable, check the MySQL service, `DATABASE_URL`, account host/grants, and local port 3306.
- If another device cannot connect, verify the same private Wi-Fi, `FLASK_HOST=0.0.0.0`, the Private firewall rule for port 5000, and a newly opened QR code. Never expose port 3306.

## Hosting boundary

`python run.py` is a local-development runner and is intended only for controlled same-LAN use. Do not expose it directly to the public internet. Internet-facing or office production hosting requires an approved WSGI/WebSocket server, HTTPS/TLS, persistent private file storage, private MySQL access, and separate live-environment operational approval.
