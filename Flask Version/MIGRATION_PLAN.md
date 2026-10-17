# Retail Genie: Flask + MySQL Migration Plan

**Status:** Phase 1 implementation is complete, with shared-office MySQL validation still pending. Phase 2 code now includes the typed 27-table MySQL landing schema, a read-only/repeatable SQLite importer, and administrator-configurable automatic MySQL backups; staging/reconciliation sign-off, uploaded-file migration, and live office-MySQL verification remain. The current schema is still single-company. New multi-company/multi-store requirements are documented in [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md), not implemented, and the tenant/store foundation must be designed and tested before Phase 3 business modules. Tests use isolated SQLite; no live office MySQL server is available here.

**Remaining phases:** Phase 2 is still in progress; Phases 3–6 have not started. Therefore five phase groups still have work (the remainder of Phase 2 plus four full phases, 3–6). Phase 1 also has one environment-validation item outstanding.

**Target directory:** `Flask Version/`
**Migration principle:** Keep `Node Js Version/` unchanged as the reference and rollback copy until the Flask version passes feature and data checks.

## 1. Current-project audit

- The current app is a **Next.js/React TypeScript application**. Node.js currently runs both the UI/server and the API routes; it is not just a small Node API that can be swapped without affecting the UI.
- The repository contains **58 API route handlers, 54 page files, and 220 TypeScript/TSX source files**. The feature set includes admin and manager tools, products/inventory, orders and checkout, quotations, demand notices, returns, purchasing/SCM, attendance/breaks, audits, internal messaging, cloud files, reports, barcode/receipt printing, and an LCD order display.
- The active database implementation is **SQLite** (`Node Js Version/netpos.db`), with **27 tables**. The checked-in snapshot currently has 12 user rows, 8 product rows, 1 order, and 2 demand notices; most other operational tables are empty. These are snapshot counts only and must not be assumed to be the production dataset.
- The UI currently reloads data by **polling every 5 seconds in production** (15 seconds on localhost), plus refreshes on tab focus. This is periodic refresh, not true push-based real-time synchronization.
- `firebase` appears in `package.json`, but no Firebase/Firestore usage was found in the application source inspected. The current persisted backend is SQLite, not Firebase Realtime Database.
- The application expects uploaded images and documents under a local `uploads/` directory. That directory is not present in this checkout; uploaded files are not necessarily included in Git and need their own backup/migration plan.
- No automated test/spec files were found in the current app. The Flask version should add tests from its first phase.

### High-priority security findings

1. The current login flow fetches a user record from a public username endpoint; that endpoint returns the password field. The existing user API also stores passwords directly rather than hashing them.
2. Some API authorization relies on a client-supplied `X-User-ID` header. A client can alter that header, so it must not be treated as proof of identity.
3. The SQLite database is tracked in Git and contains account and operational rows. Before production use, confirm whether it is demo or real data; do not commit production records or passwords.

These are reasons to redesign authentication and access control server-side, not to copy the existing login approach into Flask.

## 2. Recommended target architecture

### Strict no-Node option (recommended for the stated requirement)

- **Flask serves both the UI and backend.** Use Jinja templates, shared layout components, responsive CSS, and HTMX/vanilla JavaScript for interactive screens and small updates.
- Do not require a Node server, `npm`, or a Node-based frontend build to install or run the delivered Flask application.
- Implement versioned Flask API routes with Blueprints, while keeping ordinary page rendering in Flask. Preserve the existing screens, roles, print layouts, and workflows by using the Node version as the behavior reference.
- This is a **full UI migration as well as a backend migration**. It is larger than replacing the API alone, because the current React/Next.js UI has 54 page files.

### Shared data and real-time updates

- All devices connect to one authoritative Flask server; browser clients never connect directly to MySQL. The existing Phase 2 app uses one business database and is single-tenant. For the new multi-company requirement, the recommended design is a platform/control database plus one MySQL 8 / InnoDB database per company, with all of that company's stores sharing its tenant database and a least-privilege tenant connection. This storage choice is **recommended but not yet approved**; see [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md). A shared database with mandatory `company_id` keys is an alternative that requires explicit approval and equally strong isolation tests.
- Use SQLAlchemy 2.x and Alembic/Flask-Migrate. Store OMR money as `DECIMAL` (not floating-point), preserve stable existing IDs and document-number series, add foreign keys/indexes, and normalize important transactional data such as order lines and payments where that improves reporting and integrity. Scope every company-owned row and query to its company; scope manager data, reports, files, and events to the manager's admin-assigned store(s).
- Run sales, payments, returns, stock deductions/receipts, and document-number allocation in database transactions. Add idempotency keys to operations that may be retried so an offline retry or dropped response cannot create a duplicate sale/payment.
- Add authenticated real-time events using Flask-SocketIO (or an equivalent WebSocket/SSE design). After a database transaction commits, emit a minimal event to the correct authorized users/store, then let the UI update or fetch the changed record. Persist event/outbox rows with the transaction so a process restart does not silently lose notifications.
- Reconnect with a last-seen event cursor and fetch missed changes. Keep a slower polling/revalidation fallback for disconnected clients. If the production deployment runs multiple Socket.IO workers, use Redis only as the event fan-out/message queue; **MySQL remains the business-data database**.
- “All accounts sync” means an account receives only changes it is authorized to see within its company and store assignment. It does not mean sending passwords or sessions between accounts or exposing one tenant's events to another. Role, tenant, and store-assignment changes must take effect server-side and invalidate or refresh affected sessions.

### Authentication, files, and operations

- Add a Flask login/logout flow with Argon2id password hashes, signed `HttpOnly`/`Secure`/`SameSite` cookies, CSRF protection, login rate limits, and server-side role/permission decorators. Keep only the user ID and a revocable authentication-version marker in the signed session; reload role, permissions, and account status from MySQL. Do not trust `X-User-ID` for authentication.
- Use environment-based secrets/configuration. Do not ship default production credentials or commit `.env` files.
- Initially keep uploaded media in a configured persistent `UPLOADS_DIR`, with MySQL storing metadata and relative paths. Apply file-size/type validation and authorization checks to downloads. Back up uploads with the database; object storage can be added later if needed.
- Use a single authoritative deployment (an office server reachable by all devices, or a cloud VPS). Installing a separate Flask + MySQL database on every client would recreate the current data-isolation problem.

## 3. Phased development plan

### Phase 0 — Confirm scope and protect existing data

- [x] Confirm the checked-in SQLite snapshot is demo/sample data only; do not treat it as the production dataset.
- [ ] Identify any real SQLite database and upload/media folders; create a verified, restorable backup before conversion.
- [x] Confirm the strict no-Node requirement: no Node runtime and no Node/npm frontend build dependency.
- [x] Confirm the initial deployment target is a shared office/local-network server; confirm OS, LAN access, HTTPS/TLS, and backup placement during deployment planning.
- [x] Document the multi-company role hierarchy, admin-controlled manager/store assignments, phone-only open-bill lookup, and separate payment-class invoice series in [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md).
- [ ] Before coding the tenant schema, approve the isolation architecture, decide the manager exception/approval scope for cross-store bill continuation, clarify the daily manager “return/as per collection,” and confirm invoice-series scope/numbering time.
- [ ] Complete a role-by-role workflow inventory from the existing pages and API routes and agree the must-have features for the first usable release.

### Phase 1 — Flask foundation

- [x] Add the Flask app factory, environment configuration, request security headers, health/readiness checks, Python dependency file, and setup/run instructions inside `Flask Version/`.
- [x] Add SQLAlchemy, an initial Alembic migration, MySQL URL configuration, CSRF protection, revocable signed sessions, and a pytest suite.
- [x] Implement Argon2id login/logout, safe current-user lookup, server-side permission decorators, first-admin provisioning, and account create/activate/deactivate workflows.
- [ ] Verify two separate browsers against the same central office MySQL instance. This requires the office MySQL server/network configuration, which is not available in this workspace yet.

### Phase 2 — MySQL schema and safe data import (in progress)

- [x] Map all 27 checked-in SQLite tables into a documented MySQL/InnoDB landing schema (`LEGACY_SCHEMA_MAP.md`). Preserve stable IDs, foreign-key relationships, date/time values normalized to UTC, JSON payloads, and document-number counter rows; monetary columns use `DECIMAL` rather than floating point.
- [x] Add a read-only, immutable-source dry run and insert-only transactional importer. It checks the reviewed source schema, foreign-key integrity, JSON, numeric precision, usernames, and permission mappings. A matching existing ID is skipped; a conflict rolls back the whole import rather than overwriting target data.
- [x] Reset legacy credentials to random unknown values by default and hash them with Argon2; force a password change. An explicitly confirmed option can hash vetted legacy credentials, and operators can interactively provision a temporary password for approved imported accounts. No credentials are printed or logged.
- [x] Add the requested admin-configurable automatic MySQL backup interval, dedicated single-instance scheduler/worker, private `.sql.gz` files under `Flask Version/backup/` by default, SHA-256/run history, and configurable file retention. Backup files are ignored by Git; the worker is not started inside web workers.
- [x] Add source-to-target row-count/ID checks, target foreign-key checks, and reconciliation of order totals, nested payment amounts, aggregate product stock, and invoice-number counters; the import transaction rolls back on mismatch.
- [ ] Run the importer against an approved staging MySQL instance, independently sign off the reconciliation, and rehearse backup restore/rollback. Only offline migration generation and isolated SQLite importer tests have run in this workspace.
- [ ] Migrate uploaded files separately and verify every database path resolves to a real file. The Phase 2 importer preserves path metadata but does not copy files.

#### Multi-company/store foundation — required before Phase 3 (not implemented)

- [ ] Approve the tenant storage architecture. The current implementation is single-tenant; the recommendation is a platform/control database plus a database per company.
- [ ] Add the company/store registry, tenant resolution, company-admin hierarchy, and explicit manager-to-store assignments. Enforce the assignment in server-side page/API queries, exports, files, reports, and live events.
- [ ] Design the company-shared open-bill workflow: phone-only lookup within one company, store-of-origin versus acting/payment store, partial payments, manager-approved/audited removals, and no closure until fully settled or formally voided.
- [ ] Add independent Cash, Bank, and Bank Transfer invoice counters plus admin-configured mixed-tender classification; decide company-wide versus per-store numbering and when the final invoice number is allocated.
- [ ] Update importer/data-mapping rules so every imported company and store is explicitly identified; do not import data into production until that mapping and reconciliation are approved.
- [ ] Extend backup/restore and operational validation to cover platform data and every company database.

See [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md) for the complete requirements and acceptance checks.

### Phase 3 — Port business modules in dependency order

1. Tenant-scoped users, sessions, roles, permissions, company/store assignments, settings, and activity/audit logging (building on the Phase 2 tenant foundation).
2. Products, categories, search/barcode lookup, store-scoped stock, and CSV import/export.
3. Company-shared open orders, phone lookup, cross-store checkout/payments, manager-approved removals, mixed-tender invoice series, returns/exchanges, and receipt printing.
4. Demand notices and quotations, including conversion workflows.
5. Suppliers, purchase orders, receiving, attachments, and logistics tracking.
6. Attendance, breaks, stock audits, evidence images, messaging, cloud files, and reports.
7. LCD order display, barcode/label printing, and remaining admin screens.

For every module, port the rules and permissions, not just the visible page. Use MySQL transactions for inventory and money-changing actions.

### Phase 4 — Real-time and offline behavior

- Publish authenticated events only after successful commits; scope events by user role, recipient, and store as appropriate.
- Add client reconnect/replay, visible connection status, and safe handling of conflicts. Use optimistic UI only where the server can confirm or reject the operation cleanly.
- Keep offline queuing limited to explicitly safe, idempotent operations. A queued checkout/payment must not be replayed twice; conflicting stock changes must be reconciled rather than silently overwriting newer data.
- Test simultaneous sales, receiving, and stock changes from multiple sessions.

### Phase 5 — UI migration and feature parity

- Build shared Flask layouts, role-specific navigation, forms, tables, validation, and responsive dashboards.
- Recreate all required role workflows and preserve bilingual English/Arabic printing, OMR formatting, barcode scanning/labels, thermal invoices, and the LCD display.
- Keep the old Node app available as a comparison/reference until each feature has passed its acceptance checks. Do not delete it at the start of development.

### Phase 6 — Verification, pilot, and cutover

- Add unit, API, MySQL integration, permission/security, migration, and multi-session synchronization tests.
- Test backup and restore, large uploads, duplicate request retries, concurrent checkout/receiving, reconnect after network loss, and permission changes during active sessions.
- Pilot with a copy of real data and a small set of users. Reconcile old/new counts and financial reports before changing the primary URL.
- Cut over only after approval and a final backup. Keep a tested rollback path; retire the Node version only after Flask feature parity and data reconciliation are signed off.

## 4. Definition of done

- The `Flask Version/` app runs and is deployed without a Node server or Node build step (if strict no-Node is confirmed).
- All authorized devices use one MySQL-backed Flask source of truth; a change made by one user reaches authorized connected clients in near real time, with reconnect/replay fallback.
- Company data is isolated; managers can read only their admin-assigned store data, and the limited cross-store open-bill exception cannot grant access to other branch records or other companies.
- Company Admins and the Main Admin can administer the role/store assignments described in `MULTI_TENANT_PLAN.md`; all assignment and approval changes are auditable.
- Phone-only bill lookup works across stores within the same company; unpaid bills remain open until settled, removals/cancellations have manager approval and audit records, and Cash/Bank/Bank Transfer plus mixed-tender invoice series reconcile correctly.
- Existing required roles and workflows are covered, including sales, inventory, finance, accounts, audits, SCM, messaging/files, reports, and printing.
- Passwords are never returned by an API, stored in plaintext, or used as client-side authentication; every protected operation is checked server-side.
- Concurrent checkout, returns, and stock receiving preserve correct totals and stock; retrying the same request does not duplicate a financial operation.
- The SQLite-to-MySQL importer is repeatable and its reconciliation report matches the approved source data; upload backups and database restore have been tested.
- Automated tests cover the critical workflows, and deployment/configuration/backup instructions are documented.

## 5. Confirmed requirements and pending decisions

- **Frontend:** Follow the strict no-Node path. Rebuild the UI in Flask/Jinja with HTMX and/or vanilla JavaScript; the delivered app must not need Node or npm to run or build.
- **Deployment:** Use one shared office/local-network server as the source of truth for all devices. Confirm the server OS, LAN access, HTTPS/TLS, and backup location during deployment planning.
- **Current database:** The checked-in `Node Js Version/netpos.db` is demo/sample data, not the production dataset. Use it only for development and migration tests. If real production data or uploads are found later, back them up and assess them separately before importing.
- **Automatic backups:** An administrator configures the backup interval and retention in Flask; a separate scheduler process writes private MySQL dumps to `Flask Version/backup/` by default. Keep the backup directory persistent and private, and replicate backups off-host for disaster recovery.
- **Multi-company product requirements:** Companies are isolated tenants; each may have multiple stores. The hierarchy is Main Admin/Super Admin → Company Admin/Sub Admin → managers → sales/cashiers. Main Admin and Company Admin control manager-to-store assignments; managers see only their assigned-store data. A phone number alone finds open bills within the same company; an unpaid bill stays open until settlement. Removals/cancellations require manager approval and audit. Cash, Bank, and Bank Transfer use separate billing series; the admin preconfigures the classification for mixed-method payments. These requirements are recorded in [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md), not yet implemented.
- **Pending tenancy choices:** The user has not yet approved database-per-company versus a shared tenant-key database. The meaning of the daily manager “return/as per collection,” manager permissions for the narrow cross-store bill workflow, invoice-sequence scope, and final invoice-number allocation time also remain to be confirmed.

Phase 1 foundation code and Phase 2 schema/import/backup code are in place. The remaining Phase 2 operational checks and multi-tenant foundation must be completed before Phase 3 business modules; Phases 3–6 have not started. Keep the Node version unchanged until feature parity and final data checks are approved.
