# Gyro Pulse implementation and verification — 2026-10-31

## Status: improved implementation, NOT certified production-ready

This change closes specific verified gaps; it is not a claim that every legacy endpoint,
Android screen, financial edge case, or deployment has passed production acceptance.

## Implemented
- Removed database creation, hardcoded admin credentials and scheduler startup from WSGI imports.
- Explicit `flask --app app init-db` and interactive `create-admin` commands.
- Fixed missing auth database import and configured-day expiry calculation.
- API login issues hashed, expiring per-device keys; client sends X-Device-UUID.
- API-key authentication validates expiry and device identity. UUID is an identifier, not hardware attestation.
- Production disables shared legacy role-key authentication. Browser sessions remain separately authenticated.
- Production startup requires secret configuration; secure/HttpOnly/SameSite session cookies.
- Session-check returns JSON 401 instead of an HTML login redirect.
- Added approve/pick/pack/ready/dispatch-scan fulfillment routes with role/city checks,
  row locks, legal state transitions, rollback and inventory checks.
- Reservations remain held through picking/packing and are released only once at ready.
- QR scan URL stored in existing VARCHAR column; PNG rendered dynamically for printable labels.
- Order submissions support stable client_order_id deduplication in a new offline_submissions table.
- Order quantity, city and finite/nonnegative totals validation; customer outstanding updated on creation.
- GPC export importer accepts an `orders` array, creates real orders, returns per-order results,
  supports retry without duplicates, and restricts export owner/city. Each entry is a separate transaction.
  Payments/customer creation are NOT part of this import contract.
- Fixed unsafe permissive Base64 decoding of raw encrypted GPC bytes.
- Customer search now queries real city-scoped customer records.
- Native Android durable user-scoped order outbox, stable UUID, background retries and queued feedback added.
- Android no longer places API keys in URLs or enables HTTP BODY logging.
- Retail Genie Final's existing local CSS reused for new sign-in and operations UI.
  Existing management screens remain accessible at /dashboard/legacy; they are not fully redesigned.
- Android light-theme palette adapted to Retail Genie. This is not a complete native screen redesign.
- Tracked server .env removed from the index; local env/data/build files ignored.
  Previously committed credentials still exist in Git history and must be rotated.

## Run locally (server directory)

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-production.txt
cp .env.example .env
# Set independent SECRET_KEY and MASTER_SECRET, DATABASE_URL, and CORS origins.
flask --app app init-db
flask --app app create-admin
flask --app app run --host 0.0.0.0
```

Existing deployments: back up first; `init-db` creates the new offline_submissions table
without modifying existing columns. Review existing schema and migrations before rollout.
Production must use a WSGI server (e.g. gunicorn --bind 0.0.0.0:5000 app:app), HTTPS,
a trusted reverse proxy and explicit CORS origins. Never expose the Flask development server.
Automatic backups are no longer implicitly started in each web worker; configure a single
external scheduled backup job and rehearse MySQL restore before deployment.

## Verification

Run from the server directory: `pytest -q tests`.
Tests use SQLite in-memory databases and temporary test accounts; no real database is altered.
Coverage includes full approve-to-dispatch transitions, duplicate transition rejection,
stock reservations, invalid picking, wrong barcode, key binding/expiry, key generation/revoke,
unauthenticated session check, dashboard rendering, encryption roundtrip, idempotent order
retry/import, invalid quantities, insufficient stock, role and city boundaries.

Browser evidence in `preview/`: actual Chromium screenshots, seeded fictional demo records.
Browser checks: login, four live order rows, approve action, responsive 390px viewport.
Mobile screenshot is **mobile web**, not an Android emulator screenshot.

## Blocking work before any production sign-off
- Android SDK, JDK/Gradle and device/emulator builds are unavailable here. Compile and instrument
  outbox/WorkManager/GPC import, process death, camera scanning, cancellation and account switching.
- Native GPC export UI must be wired to the new orders-array import contract; do not assume
  the existing message/token export already serializes queued sales orders.
- Outbox needs visible rejected-order review/edit/retry UI and encrypted local storage policy.
- Messaging inbox/poll/responses/sync-status legacy endpoints remain stubs. Other legacy client
  endpoints and Socket.IO initialization still need a full contract audit.
- Authenticated encryption/versioned GPC migration, per-device secrets, strict token replay and
  expiry consumption, master-secret distribution review remain necessary. Legacy CBC payloads
  are not authenticated and a shared master secret is not a production-grade trust model.
- Full CSRF protection, login throttling, dependency/security audit, upload validation, backup ZIP
  extraction security and restore-drill, session invalidation and per-endpoint object authorization.
- Concurrent MySQL/InnoDB stress tests: duplicate order races, inventory locks, transfers, returns,
  settlement segregation, payment idempotency, credit-limit serialization, finance reconciliation.
  SQLite tests do NOT prove production row-locking or concurrent request behaviour.
- Complete city/tenant scoping across all existing routes; broad existing API/admin routes were
  not all audited or rewritten by this change.
- Full Retail Genie UI adaptation of legacy management pages and all native Android screens.
- Deployment health/readiness, migrations, observability, alerting, scheduled backup worker,
  key rotation, load testing and user acceptance of end-to-end delivered/payment workflows.
