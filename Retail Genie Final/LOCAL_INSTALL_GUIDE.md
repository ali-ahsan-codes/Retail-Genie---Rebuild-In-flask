# Retail Genie — Local installation

This guide installs Retail Genie on a Windows PC using MySQL Community Server. It also describes same-Wi-Fi access for phones and tablets using the app's dynamically generated QR code.

## 1. Install the prerequisites

On the PC that will run Retail Genie, install:

- Python 3.11 or newer
- MySQL Community Server 8.0.16 or newer with InnoDB
- Git, if cloning the repository

In PowerShell, confirm that the MySQL service is running:

```powershell
Get-Service *mysql*
```

If needed, start the MySQL service from Windows Services or from elevated PowerShell with `Start-Service MySQL80` (the service name can differ).

## 2. Install the application and database

Open PowerShell at the repository location:

```powershell
cd "path\to\Retail-Genie"
.\install.ps1
```

The installer creates a virtual environment, installs the Python requirements, and provisions only the `retail_genie` database. It reuses the MySQL connection credentials in the existing `.env` for provisioning when possible; the database name in that URL is ignored. If that account cannot create databases and users, the installer asks for a MySQL administrator login. It generates a separate, least-scope `retail_genie_app` account and writes Retail Genie settings to `.env.retail-genie`.

The existing `.env` is not modified. Retail Genie does not use its `DATABASE_URL`, so an unrelated database such as `invoiceflow_v2` is never used by the app. Do not expose MySQL port 3306 to client devices or the internet.

If PowerShell blocks the script, run it from PowerShell with:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer applies `database-schema.sql` only to a new or empty Retail Genie database. If the database already contains a partial schema, it stops without altering those tables.

During installation, `seed_admin.py` prompts you to create the first Main Admin. Edit its `ADMIN_USERNAME` value before running it to choose a different username. Set a unique password of at least 12 characters when prompted; the password is not stored in the Python file.

To create the Main Admin later, run:

```powershell
.\.venv\Scripts\python.exe seed_admin.py
```

Optional: add sample company/store/products and opening inventory for a **fresh local development database only**:

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi seed-demo --confirm-demo-data
```

This explicit command is restricted to a local MySQL database named `retail_genie`; it refuses to run if business records already exist. It adds one demo tenant, one company, one store, five sample products, and demo-only opening stock. It does not create a login account or sales/customer history. Skip it for a real installation.

## 3. Start Retail Genie

```powershell
.\.venv\Scripts\python.exe run.py
```

Keep the PowerShell window open. On the server PC, open `http://127.0.0.1:5000/`. The `/healthz` page reports app health; `/readyz` checks the MySQL connection. Sign in using the Main Admin account created above.

## 4. Share the login page with the QR code

The **Open on phone** QR panel appears for desktop, laptop, and tablet browsers. Phone browsers do not show the QR panel. The code points to the current login address; it is generated as the app is opened, so a daily LAN IP change does not require a hard-coded URL in the app.

For phones/tablets on the same trusted private Wi-Fi:

1. Connect the server PC and the client devices to the same non-guest Wi-Fi/LAN.
2. In `.env.retail-genie`, set:

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
4. Restart `.\.venv\Scripts\python.exe run.py`.
5. On the server PC, open `http://127.0.0.1:5000/login`, select **Open on phone**, and scan the QR with the phone/tablet camera.
6. Keep the phone/tablet on the same Wi-Fi/LAN and sign in with an account created by the Main Admin.

If the PC's address changes, reopen the local login page on the PC and scan the refreshed QR. If several network adapters are present and the detected address is not reachable by clients, use `ipconfig` to identify the correct Wi-Fi/Ethernet address and set `PUBLIC_BASE_URL=http://<current-lan-ip>:5000` in `.env.retail-genie`, then restart the app. For reverse-proxy or DNS hosting, set `PUBLIC_BASE_URL` to the full externally reachable base address, including HTTPS when configured.

## 5. Set up tenant users

1. Sign in as Main Admin.
2. Use **Companies** to add a tenant company, its first store, and its Company Admin.
3. Use **Accounts** to create staff accounts, assign roles/permissions, and grant only the required store access.
4. Each independent customer belongs in a separate logical tenant container within the shared MySQL database.
5. If using subscription plans, add a plan under **SaaS plans** and explicitly assign it under **Tenant subscriptions**. Existing tenants without a plan remain unmetered.

## Start/stop and troubleshooting

- Start from the repository root: `.\.venv\Scripts\python.exe run.py`.
- Stop: press `Ctrl+C` in the runner window. MySQL runs as a separate Windows service.
- If `/readyz` is unavailable, check the MySQL service, `.env.retail-genie`, account host/grants, and local port 3306.
- If another device cannot connect, verify the same private Wi-Fi, `FLASK_HOST=0.0.0.0`, the Private firewall rule for port 5000, and a newly opened QR code. Never expose port 3306.

## Hosting boundary

`.venv\Scripts\python.exe run.py` is a local-development runner and is intended only for controlled same-LAN use. Do not expose it directly to the public internet. Internet-facing or office production hosting requires an approved WSGI/WebSocket server, HTTPS/TLS, persistent private file storage, private MySQL access, and separate live-environment operational approval.
