# Phase 6 — Verification, pilot, and cutover acceptance

**Status: In progress.** Starting Phase 6 does not authorize access to production data, schema changes on an office database, a live import, or cutover. No production system has been modified. Phase 6 must remain open until evidence is recorded for every required gate and the user approves cutover.

## Current environment

- The local regression suite and migration checks use isolated SQLite; they do not represent MySQL acceptance.
- This workspace has no MySQL client/server, Docker runtime, configured MySQL test URL, or reachable service on `127.0.0.1:3306`.
- Consequently, no live MySQL, staging, two-browser office-network, MySQL concurrency, real backup/restore, approved-media, or pilot-data test has been run.
- Do not put database credentials, production data, customer files, backups, or secrets in Git or chat. Supply connection settings only through the approved secure environment on the staging host.

## Safe local work

- [x] Preserve the Node application unchanged as a reference and rollback copy.
- [x] Complete Phase 5 local verification (145 tests at Phase 5 closure).
- [x] Add `flask --app wsgi phase6-preflight`, a read-only check for MySQL 8, current Alembic heads, mapped-table presence/InnoDB, and session foreign-key enforcement. It rejects non-MySQL targets before issuing SQL and never changes schema or data.
- [x] Run the updated full local suite including Phase 6 preflight tests: 146 passed.
- [x] Verify fresh SQLite migration upgrade, schema check, explicit reversible downgrade to `ba2fd4c7e8a1`, re-upgrade, and current revision `f4c1b7a2d903`.
- [ ] Run the preflight against an approved staging MySQL database and retain its sanitized output as evidence.

## Required deployment acceptance gates

### A. Environment and schema

- [ ] Confirm the app-server OS, persistent paths, TLS/reverse proxy, firewall, DNS/LAN URL, and monitored service manager.
- [ ] Create or identify a disposable staging MySQL 8/InnoDB database with an approved test account. Never target production for rehearsal.
- [ ] Take and independently verify a pre-migration staging backup.
- [ ] Review Alembic heads and apply migrations only to the approved staging database; capture `flask db current`, `flask db heads`, and preflight output.
- [ ] Confirm all mapped application tables exist, use InnoDB, and enforce foreign keys.

### B. Migration/data reconciliation

- [ ] Use an approved consistent source snapshot; do not import from a live SQLite database or one with uncheckpointed WAL data.
- [ ] Run importer dry-run first; reconcile row counts, stable IDs, tenant/company/store scoping, OMR totals, invoice counters, order/payment/refund totals, stock balances, and audit/movement totals.
- [ ] Apply only to disposable staging after reviewing dry-run evidence; repeat reconciliations against the imported destination.
- [ ] Migrate approved uploaded media separately; verify hashes, scoped paths, access control, manifests, and orphan reports.

### C. Runtime, browser, security, and workflow

- [ ] Start the app and the single backup scheduler as separate managed processes; verify liveness/readiness and logs contain no secrets.
- [ ] Use two independent browsers on the same office URL and central MySQL. Verify shared authorized changes, isolated sessions, cross-tenant denial, role/store boundaries, active permission revocation, reconnect/replay, and visible stale-data handling.
- [ ] Validate HTTPS, secure/HttpOnly/SameSite cookies, CSRF, CSP, login throttling, uploads, and backup path permissions on the actual deployment.
- [ ] Test the role/workflow inventory with representative accounts; exercise checkout, refunds/exchanges, receiving, cashup, audit, reports, print and LCD on real devices.
- [ ] Check supported browsers, barcode scanners, label printers, 80 mm thermal printer/PDF output, Arabic font rendering/RTL, and OMR three-decimal receipts.

### D. Backup, restore, concurrency, and go/no-go

- [ ] Create a real MySQL backup via the configured worker; verify gzip integrity and SHA-256, then copy it to separate protected storage.
- [ ] Restore the backup into a separate disposable MySQL database. Verify schema revision, counts, financial/inventory reconciliations, and app readiness before recording evidence.
- [ ] Run concurrent checkout, payment, return, receiving, and stock adjustment operations with separate sessions/workers. Verify no duplicate invoice/order numbers, oversell, balance drift, duplicate retry effects, or audit gaps.
- [ ] Exercise reconnect after network loss and permission changes during active sessions; verify financial operations remain online-only.
- [ ] Pilot only from an approved staging copy with a small user group; collect sign-off and a rollback rehearsal.
- [ ] Obtain explicit cutover approval, take a final verified backup, preserve the rollback URL/data path, and only then change the primary URL. Do not retire the Node app until parity and reconciliation are signed off.

## Evidence log

| Gate | Evidence/artifact | Result | Date / approver |
|---|---|---|---|
| Local automated suite | `.venv/bin/python -m pytest -q` | 146 passed | 2026-10-21 |
| Staging MySQL preflight/migrations | Not available in this workspace | Blocked on approved staging MySQL | — |
| Import/media reconciliation | No approved production snapshot/media available | Pending | — |
| Two-browser/device workflow | No office network/devices available | Pending | — |
| MySQL backup and isolated restore | No MySQL service/client available | Pending | — |
| True MySQL concurrency | No MySQL service available | Pending | — |
| Pilot/cutover approval | Not authorized | Not started | — |
