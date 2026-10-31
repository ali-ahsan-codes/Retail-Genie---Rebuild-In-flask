# Phase 1 — safe local application guide

## What applying this phase means

Install TWO fresh, isolated development applications. They do not sync yet. Do not replace an
existing Retail Genie/Gyro deployment, import business data or expose these copies publicly.
No copy or verification command below creates a production database automatically.

## 1. Review first

- Check SOURCE_MANIFEST.json and BASELINE_REPORT.md.
- Ports: office 5100; field server 5200. Check these are free.
- Fresh databases: `retail_genie_hybrid` and `gyro_pulse_hybrid` with separate DB users.
- Keep virtual environments and app process environment variables separate.
- Do NOT point DATABASE_URL at `retail_genie`, an existing Gyro database, or any live database.
- Never copy source deployment .env files, tokens, media, backups or mobile signing keys.

## 2. Verify clean sources (no dependencies required)

From `gyro-pulse-with sales system/`:

```sh
python -m unittest discover -s integration/tests -v
```

These source-hash checks intentionally describe Phase 1's snapshot. Future approved code
changes require explicit manifest updates or a new phase manifest; do not overwrite original
source folders to make a test pass.

## 3. Independent virtual environments

Windows Python example, run each command in its indicated app directory:

```powershell
# retail-genie/
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# gyro-pulse/server/ (a DIFFERENT .venv)
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

On Linux/macOS substitute `python3 -m venv .venv` and `.venv/bin/python`.
Inherited requirements differ (Retail Flask 3 versus Gyro Flask 2). Dependency modernization
and security audits are separate gates; installation success does not certify production safety.

## 4. Optional no-business-data smoke checks

Run from this hybrid root, BEFORE creating .env.retail-genie:

```powershell
.\retail-genie\.venv\Scripts\python.exe integration\baseline_smoke.py retail
.\gyro-pulse\server\.venv\Scripts\python.exe integration\baseline_smoke.py gyro
.\gyro-pulse\server\.venv\Scripts\python.exe -m pytest -q gyro-pulse\server\tests
```

The smoke tool forces an in-memory database and disables Retail background dispatch. It refuses
to load an existing Retail config because that loader intentionally overrides process variables.
Retail readiness here verifies SELECT 1 only; no business tables, MySQL or real user flows.

## 5. Fresh local office installation (explicit opt-in)

Only after confirming that `retail_genie_hybrid` is a new test database:

- Use the COPY's `retail-genie/install.ps1`, not the original installer.
- It prompts locally for MySQL administration and provisions `retail_genie_hybrid` and
  `retail_genie_hybrid_app`; it writes copy-local `.env.retail-genie` and prompts for an admin.
- It does not migrate existing business data. Review the script/schema before running.
- For manual setup, copy `.env.example` to `.env.retail-genie`, generate a strong SECRET_KEY,
  use the fresh isolated MySQL URL and apply only the COPY's schema to that empty database.
- Local default port: 5100. Start `python run.py` using the office environment.
- Inherited `seed-demo` is guarded for the upstream database name and is NOT approved for this
  hybrid database. Do not bypass its protection; a hybrid-specific demo provisioner is future work.

## 6. Fresh Gyro server installation (explicit opt-in)

- Work in `gyro-pulse/server/`, use that app's environment.
- Copy `.env.example` to `.env` and set independent SECRET_KEY and MASTER_SECRET values.
- SQLite `gyro_pulse_hybrid.db` is for development; intended MySQL test DB is `gyro_pulse_hybrid`.
- Run `python -m flask --app app init-db` only against a fresh test database.
- Run `python -m flask --app app create-admin` to provision a test administrator.
- Run `python app.py`; development port 5200. Public liveness: `/health`.
- Do not run inherited flush/restore/migrate/reset helpers against live data. They are copied
  baseline tools, not reviewed hybrid migration commands.
- Do not configure production pairing/base URLs or publish keys yet; Phase 2 handles that contract.

## 7. Android

Open `gyro-pulse/android/` in Android Studio on a machine with the matching Android SDK/JDK.
No local.properties, SDK, keystore or signed APK is distributed in this phase. No Android build
was run here. Use a throwaway test account/server only; hybrid fallback/pairing is NOT implemented.
Camera permissions, WorkManager, GPC import and offline recovery require later device tests.

## Rollback / approval gate

Stop copied processes and disable any manually scheduled copied jobs. Originals are unchanged.
Do not drop databases automatically: inspect and preserve any test records first. Revoke any
manually created test credentials if no longer needed. No migration rollback or live data merge
is required because this phase must not touch existing deployment data.

After local review, approve Phase 2 separately. No background connector is running in Phase 1.
