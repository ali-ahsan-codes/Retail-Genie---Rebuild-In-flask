# Phase 2B — scoped office enrollment (rebuild)

## What this implements

Only the isolated copies change. One dedicated Gyro company/instance/database is paired
with **one authoritative Retail office identity**, with one currently active connector credential.
The office UUID identifies this Retail installation, not a second stock ledger, mobile device,
warehouse allocation or independently writable branch replica.

- Company UUID is the actual authorized native Retail company ID, not a browser-supplied tenant.
- Cloud company/instance/public origin come from the persisted Phase 2A binding and configuration.
- Administrator issues a **10-minute, single-use grant**; only its SHA-256 digest is stored.
- Exchange returns a **30-day, 256-bit random bearer** once. Cloud stores its digest only.
- Only `connection:read` is granted, for `/api/v1/integration/status` metadata.
  It is NOT a catalog/order/upload/finance/device/legacy-role authorization.
- Replacement grant invalidates older pending grants, but leaves the current bearer active until
  successful replacement exchange. Exchange atomically consumes the grant, revokes the old bearer,
  stores the new digest, updates the office pointer and appends audit evidence.
- Administrator can revoke all office bearers **and pending grants**. Expiry is checked on each use.
- Company, instance and office headers must match the active scoped credential.
- Cloud UI checks active administrator and session CSRF; Retail UI reuses native login,
  company-admin permission, tenant resolution and Flask-WTF CSRF.
- Cloud audit records issue/exchange/revoke IDs and administrator where applicable. Retail audit
  records initialized office and stored credential IDs/actor. Neither contains raw secrets.
- Native bearer storage uses authenticated Fernet encryption under an **independent configured key**.
  There is no plaintext/shared-master-secret fallback. Browser receives no bearer.
- Native enrollment permits only administrator-configured, exact HTTPS origins, default TLS
  verification, no redirects and no environment HTTP proxies. Bundle addresses are not trusted
  destinations. No LAN discovery/fallback exists, and no cloud secrets are sent to unknown LAN.
- Requests/responses have bounded JSON parsing, reject duplicate keys and unsupported schemas/scopes.
  Secret-bearing UI/API responses are `no-store`; no secret is generated in a URL or audit message.

**Business sync and production remain disabled.** Phases 3–7 are still missing/unaccepted.
Earlier chat's later-phase tests are not current evidence. Phase 8 is still gated.

## Local setup — disposable isolated pilot only

Do not run these against original production databases. Back up isolated pilot databases first.
Use **separate** Python environments for the two applications, and install each copy's requirements.
No factory import starts a worker, initializes tables or enrolls an office.

1. Set up the dedicated Gyro copy using `RECOVERY_2A.md`. Its `GYRO_COMPANY_ID` must be the
   native Retail company UUID that will be selected below. Use independent strong secrets,
   separate database and explicit `GYRO_INSTANCE_ID` / `GYRO_PUBLIC_BASE_URL` HTTPS origin.
   Do not adopt/rebind a populated database or switch it to standalone to bypass guards.
2. For an **existing already-bound 2A pilot**, in `gyro-pulse/server`, add only the pairing tables:
   ```sh
   python -m flask --app app init-field-pairing
   ```
   For a **new empty pilot**, follow the 2A sequence (`init-db`, `init-deployment-binding`,
   `bind-company --confirm-empty-database`, then `create-admin`). The newly imported pairing
   models are included in `init-db`. Never initialize native business tables in the Gyro database.
3. In the native Retail process environment set:
   ```dotenv
   FIELD_GYRO_ALLOWED_ORIGINS=https://your-dedicated-cloud.example
   FIELD_INTEGRATION_KEY=<independent Fernet key from your secret manager>
   ```
   Multiple operator-approved company-cloud origins can be comma-separated. Copy the exact
   configured origin; there is no wildcard, browser override or automatic address discovery.
   Generate a Fernet key in a controlled terminal using that environment's cryptography package:
   ```sh
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Keep it out of Git/chat/logs. Losing it prevents decrypting stored bearers; use a fresh cloud
   grant to replace the credential. Changing it does **not** automatically re-encrypt old records.
4. In `retail-genie`, using its own environment/database:
   ```sh
   python -m flask --app retail_genie init-field-integration
   ```
   This creates only `hybrid_field_connections` and `hybrid_field_integration_audit`; it does not
   bootstrap/reset native business data. There is no automatic adoption or destructive migration.
5. Native company administrator opens `/settings/field-integration`, selects an authorized company
   through the existing session; native super-admin can use `?company_id=<native-company-uuid>`.
   Initialize the stable office identity. Share **company UUID and office UUID**, not credentials,
   privately with the matching dedicated cloud administrator.
6. Cloud administrator signs in through `/login`, opens `/integrations`, enters this office UUID,
   and issues a grant. It is displayed once as JSON. Copy it privately to the native enrollment
   form within ten minutes. Never share the code in a query string, ticket or public chat.
7. Native enrollment validates destination/identities and local encryption key **before network
   exchange**, consumes the grant through verified HTTPS and encrypts the returned bearer locally.
   The page displays stored metadata, not a live heartbeat or proof of ongoing connectivity.
8. Rotation: issue a new grant for the **same** office and enroll again. Cloud/office reassignment
   is intentionally blocked; it needs a separately reviewed migration. Emergency stop: cloud
   **Revoke** immediately disables active credentials and outstanding grants.

Do not expose an unencrypted HTTP listener publicly. Real TLS termination, upstream limits and
trusted proxy configuration need operator review; no forwarded header is blindly trusted here.
Apply edge request/login/pairing throttling before any external pilot: distributed rate limiting
and load/security acceptance are **not** supplied by this metadata-only implementation.

## Protocol

`POST /api/v1/pairing/exchange` accepts exactly the UI JSON fields:
`schema_version`, `company_id`, `instance_id`, `office_id`, `base_url`, `grant_id`,
`pairing_code`, `expires_at`, `scopes`.

`GET /api/v1/integration/status` requires:
```
Authorization: Bearer <scoped-secret>
X-Company-ID: <bound-company-uuid>
X-Instance-ID: <bound-instance-uuid>
X-Office-ID: <paired-office-uuid>
```
Never reuse this bearer as a mobile/device key or on inherited stock/order endpoints.
The pairing grant is not a refresh token. Grant replay, expiry, revocation or wrong identity
returns generic 401 without leaking which secret check failed. Missing pairing tables give 503.
Legacy business access remains blocked by the dedicated guard.

### Failure and recovery semantics

- Grant consumption, old-bearer revocation and new digest/audit are one cloud transaction.
- Retail releases its read transaction before HTTPS; it does not hold DB locks over network I/O.
- Cloud commit can succeed while its response or native encrypted write fails. The lost raw
  bearer is intentionally unrecoverable from cloud hashes. **Issue and exchange a fresh grant**;
  replacement revokes the lost bearer. Do not replay a consumed grant or clear the binding.
- Table creation is additive, explicit and `checkfirst`; no live schema migration was performed.
- Rollback: revoke office access, stop the copied service, preserve binding/DB/audit and encrypted
  state, restore tested application code. Do not delete records or enable legacy writers.
- Back up the encryption key independently with restricted access. Rehearsed restore, key
  re-encryption procedures, schema upgrades and MySQL concurrency are later acceptance gates.

## Current evidence (SQLite/unit checks, not deployment acceptance)

Commands run with isolated environments:
```
# Gyro environment, from gyro-pulse/server
python -m pytest -q
# Retail environment, from isolated root
python -m pytest -q retail-genie/tests
# Dependency-free source/isolation and recovery checks, from isolated root
python -m unittest discover -s integration/tests -v
# Each with its own environment
python integration/baseline_smoke.py gyro
python integration/baseline_smoke.py retail
python -m pip check
```

Final verified run: **86 tests passed** — **53 Gyro**, **21 native Retail**, and **12
foundation/recovery**. Both factory/liveness smoke checks and both `pip check` runs passed;
`git diff --check` is clean. Gyro reports 68 existing-style SQLAlchemy legacy-query warnings.

Tests cover grant exchange/replay, rotation,
revocation, expiry, company/instance/office mismatch, scope/version tampering, legacy-key refusal,
CSRF and active-admin checks, duplicate JSON/size limits, explicit schema setup, native encrypted
storage/audit, untrusted cloud/LAN refusal before network, disabled redirects, invalid response
refusal and matching mirrored contract files. Native HTTPS responses are mocked in office unit
checks. Original source hashes and unchanged 2A evidence are retained through a chained 2B overlay.

**Not run/accepted:** actual HTTPS integration/deployed browser flow, native multi-tenant UAT,
MySQL locking/concurrent exchange/load, native Android, durable transport, catalog/order approval,
backup/restore drills or business sign-off. No production/release claim follows from these tests.
