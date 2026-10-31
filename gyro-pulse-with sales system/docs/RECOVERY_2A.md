# Checkout recovery — actual evidence, 2026-10-31

## Important correction

This checkout/branch contained Phase 1 only. Its saved `phase-status.json` said implemented phase 1;
no later transport/catalog/order/mobile/release files or manifests were present. Local Git reflog,
unreachable-object check, workspace search and the previous remote branch did not recover that code.
Earlier chat claims of 181/189/204 checks are **not current-checkout verification**. They must not
be used to approve release. This recovery starts from actual files, preserves originals and does
not pretend missing code/tests have been restored.

## Reimplemented now: dedicated-company guard (2A)

In the isolated Gyro copy:

- Explicit `GYRO_DEPLOYMENT_MODE=dedicated`, canonical company/instance UUIDs, HTTPS public origin,
  separate explicit database URL and a 32+ character independent session secret are required.
- Production additionally requires MySQL/PyMySQL and a 32+ character JWT secret; these are minimum
  configuration checks, not randomness/deployment/security certification.
- CORS defaults to the explicit public origin, not `*`; wildcard/credential/path/query/fragment/bad
  port/encoded-host origins are rejected. User-supplied forwarding headers are NOT trusted by default.
- Persistent singleton binding freezes company, instance and public origin to the database.
  Runtime absent/mismatched binding returns 503, without creating schema or auto-adopting data.
- Explicit binding refuses nonempty business tables, unknown tables or identity reassignment.
  Identical re-binding is a no-op; there is no reset/drop/reassign command.
- All legacy business endpoints, including stock mutations, fulfillment, media reads and GPC paths,
  are blocked in dedicated mode. Only liveness, login/logout and a metadata-only hybrid status
  endpoint are available. There is no stock bridge, connector credential or business sync yet.
- Factory/liveness performs no schema initialization or scheduled work. Standalone baseline
  behavior remains available for regression only; it is NOT connected-company mode.

## Test-only setup

Use only a NEW, separate disposable Gyro database, never an existing company database. Do not
point the Gyro URL at Retail's database. Copy `.env.example` into private `.env` and configure:

- `GYRO_COMPANY_ID`: the approved canonical Retail company UUID, not a fabricated customer mapping.
- `GYRO_INSTANCE_ID`: fresh deployment UUID, stable across restart.
- `GYRO_PUBLIC_BASE_URL`: approved canonical HTTPS origin.
- `DATABASE_URL`: dedicated empty test DB (SQLite is permitted for local tests, not production).
- Strong independent secrets generated locally; never paste secrets into chat or commit them.

In `gyro-pulse/server` with its Python environment:

```sh
python -m flask --app app init-db
python -m flask --app app init-deployment-binding
python -m flask --app app bind-company --confirm-empty-database
python -m flask --app app create-admin
```

Schema setup/binding is explicit and must precede admin/business rows. Do not use `init-db` as a
live upgrade. No running service, pairing or production database was configured in this session.
`GET /api/v1/hybrid/status` reports identity and `business_sync_enabled=false` after valid binding.
`/health` is liveness only, not binding readiness or production acceptance.

Rollback: stop the copied service and retain its DB/binding. Do NOT switch a connected company
back to standalone to bypass a blocked writer. Do not delete binding rows or regenerate UUIDs.
Identity/key/schema migration needs explicit reviewed tooling in subsequent recovery work.

## Current verification

- Actual Gyro suite: **31 passed** (17 dedicated-mode cases plus 14 baseline cases).
- Foundation/recovery checks: **10 passed**; source originals and recovery overlay hashes checked.
- Retail factory `/healthz` + `/readyz`: passed without schema initialization.
- Gyro factory `/health`: passed without schema initialization.
- Both isolated Python environment `pip check`: no broken requirements.
- The copied Retail tree currently has no backend `tests/` directory; no Retail pytest pass count
  is claimed. A discovery attempt correctly failed, rather than yielding an invented green result.

**41 tests passed on the current code**, plus the factory/dependency checks above. No live MySQL,
Android APK/device run, cross-app order protocol or restore/UAT evidence has been reestablished.

## Remaining recovery, not silently declared complete

1. 2B: scoped expiring connector credentials, single-use pairing, issue/rotate/revoke UI/CSRF/audit.
2. 3: durable inbox/outbox/ACK/cursor/retry/quarantine in both apps, transaction ownership.
3. 4: office-owned catalog/stock snapshots and mappings, no second stock ledger.
4. 5: immutable field intents + native human approval with one stock/bill allocation and business key.
5. 6: isolated Android outbox/identity, signed encrypted cloud/LAN/file reconciliation.
6. 7: real MySQL/Android, coordinated restore, security and business acceptance against that code.

`python integration/recovery_readiness.py` lists missing source and currently exits 1. It is a
file inventory, not proof of functionality; even placeholder files cannot permit release.
Phase 8 finance/delivery/returns remains gated. `production_ready=false` and connector disabled.

All modifications are in the isolated copy on the fixed current Arena branch. Phase 1 source
manifest is unchanged; `RECOVERY_2A_MANIFEST.json` records this recovery overlay separately.
