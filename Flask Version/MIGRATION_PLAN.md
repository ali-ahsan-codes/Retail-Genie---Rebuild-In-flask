# Retail Genie: Flask + MySQL Migration Plan

**Status:** The Python/Flask foundation, SQLite importer, MySQL backup worker, tenant-container foundation, and in-progress sales/billing module exist in the working tree. The user confirmed a SaaS architecture with **one shared MySQL database, a distinct logical container per independent customer, and nested companies/branches** and authorized phased implementation after documentation. The user has now approved company-level sharing as the starting default and Main Admin-only domain-policy changes. The current tenancy foundation preserves each legacy company as its own container, uses explicit memberships and container-scoped keys, and has passed the local full suite (78 tests), a SQLite backfill/FK rehearsal, `flask db check` with no schema drift, and offline MySQL DDL generation. This remains unfinished and not production-validated: live MySQL, broad module/page/export/file/realtime coverage, backup restore, staging, and deployment checks remain outstanding. See [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md) and [`MULTI_TENANT_PLAN.md`](MULTI_TENANT_PLAN.md); do not present it as production-ready.

**Remaining work:** Close tenant-foundation policy and production-validation gates, then continue the business modules phase by phase; implement realtime/feature parity; complete MySQL/staging/restore checks and production-pilot validation. The current task remains the tenant-container foundation; no next business-module phase has started.

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

- All devices connect to one authoritative Flask server; browsers never connect directly to MySQL. The confirmed SaaS deployment uses **one shared MySQL database for all logical tenant containers**. Each independent customer has a hard `tenant_container_id` boundary; companies/child companies and branches/stores are organization units inside it. Do not create one database per customer and do not treat `company_id` as the final tenant key. See [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md).
- Use SQLAlchemy 2.x and Alembic/Flask-Migrate. Store OMR money as `DECIMAL` (not floating-point), preserve stable existing IDs and document-number series, add foreign keys/indexes, and normalize important transactional data such as order lines and payments where that improves reporting and integrity. Scope every tenant-owned row/query/event by `tenant_container_id`, then enforce configured data-domain sharing, company hierarchy, role permissions, and store assignments. Use composite foreign keys so a record cannot point to another container.
- Run sales, payments, returns, stock deductions/receipts, and document-number allocation in database transactions. Add idempotency keys to operations that may be retried so an offline retry or dropped response cannot create a duplicate sale/payment.
- Add authenticated real-time events using Flask-SocketIO (or an equivalent WebSocket/SSE design). After a database transaction commits, emit a minimal event to the correct authorized users/store, then let the UI update or fetch the changed record. Persist event/outbox rows with the transaction so a process restart does not silently lose notifications.
- Reconnect with a last-seen event cursor and fetch missed changes. Keep a slower polling/revalidation fallback for disconnected clients. If the production deployment runs multiple Socket.IO workers, use Redis only as the event fan-out/message queue; **MySQL remains the business-data database**.
- “Sync” means authorized memberships in the same tenant container use the same canonical rows and receive permitted change notifications; it is not database copying. An account receives only events allowed by its container, data-domain policy, company/branch membership, role actions, and store assignment. No event crosses containers. Role, policy, tenant-membership, and assignment changes must take effect server-side and invalidate or refresh affected sessions/subscriptions.

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
- [x] Confirm a SaaS shared-database architecture with one logical tenant container per independent customer and child companies/branches inside a container; see [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md).
- [x] Confirm that the Super Admin controls manager cross-store open-bill policy and that daily manager “return/as per collection” means cash/bank end-of-day closeout.
- [x] Document tenant isolation, roles, domain-sharing policy, lifecycle, migration order, and acceptance criteria before continuing implementation.
- [ ] Review the remaining architecture decisions: child-company admin scope, whether multi-container staff is operationally allowed, and invoice-series scope/allocation timing. The initial company-level sharing default and Main Admin-only policy authority are now confirmed.
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

#### SaaS tenant-container foundation — implemented locally; production gates remain

- [x] Confirm one shared MySQL database and a logical tenant container per independent customer; nested companies and branches belong to a selected container.
- [x] Document the hierarchy, data-domain policy, role/branch authorization, lifecycle, migration strategy, open decisions, and acceptance criteria in [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md).
- [x] Add `tenant_containers`, nested company relationships, active container memberships, container-scoped store assignments, domain policies/scopes, and same-container composite foreign keys.
- [x] Backfill each pre-existing company into its own container so the earlier company isolation is not silently weakened; test two-company data, membership, assignment, billing-series and audit backfill with SQLite foreign-key checks.
- [x] Implement server-side active-container selection, explicit multiple-membership selection, role/store scoping, action-level domain grants, and tenant-aware importer and sales/billing queries/records.
- [x] Add cross-container API/service and in-container policy/action tests; the current full local suite passes. This does not yet cover all pages, products/inventory, exports, files, reports or realtime events.
- [x] Generate offline MySQL DDL and verify the fresh SQLite Alembic chain and `flask db check` locally. A live MySQL server is not available in this workspace.
- [x] Confirm company-level sharing as the starting default and Main Admin as the only role allowed to change domain policies.
- [x] Add Main Admin-only policy index/editor, company/container/assigned-store/selected-unit/disabled modes, selected-unit allow/deny lists, policy versioning, and before/after tenant audit history.
- [ ] Enforce/verify per-domain scopes across every future module and invalidate/re-authorize active realtime subscriptions when permissions change; current HTTP requests read the latest policy state.
- [ ] Run the migration, foreign-key, importer reconciliation, backup/restore and concurrency rehearsals on approved staging MySQL; do not use the checked-in sample SQLite database as production data.
- [ ] Migrate uploaded files separately and design/test any filtered tenant export/restore so one tenant operation cannot affect another.

### Phase 3 — Port business modules in dependency order

**Status:** Phase 3 business-module porting has not started as a distinct phase. A sales/billing/cashup draft existed earlier and is now tenant-scoped, but remains incomplete; product catalog/inventory have not begun. The active work is still the tenant-container foundation under Phase 2. Do not start Phase 3 until that foundation's acceptance gates are met.
1. Tenant-container-scoped users, sessions, memberships, roles, domain-sharing policies, company/branch assignments, settings, and audit logging.
2. Container-aware products, categories, search/barcode lookup, policy-scoped inventory, and CSV import/export.
3. Container/policy-scoped open orders, phone lookup, cross-branch checkout/payments, manager-approved removals, mixed-tender invoice series, returns/exchanges, and receipt printing.
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

- The `Flask Version/` app runs without a Node server or Node/npm build step.
- All authorized devices use one MySQL-backed Flask source of truth. Permitted changes reach authorized clients in near real time, with reconnect/replay fallback.
- The shared database enforces an immutable `tenant_container_id` boundary. A child company or branch can be added inside a selected container, but no user, business row, file, report, export or live event can cross into another independent customer's container.
- Container data-domain policies and role actions work together: enabling a domain does not grant every role access, and a role permission cannot bypass a disabled/narrowed sharing policy or a branch assignment.
- Main Admin and delegated tenant/company admins can administer only their documented scope. Manager assignments and privileged policy/approval changes are auditable and take effect on active sessions/subscriptions.
- Phone-only open-bill lookup and continuation stay inside the active container and configured domain scope. Unpaid bills remain open until settled or formally voided; removals/cancellations have authorized manager approval and audit records.
- Cash, Bank, Bank Transfer and configured mixed-tender invoices reconcile under the approved sequence scope/timing policy.
- Required feature parity covers sales, inventory, finance, accounts, audits, SCM, messaging/files, reports and printing.
- Passwords are never returned by an API or stored in plaintext; every protected operation is checked server-side.
- Concurrent checkout, returns and stock receiving preserve totals; an idempotent retry does not duplicate a financial operation.
- Import, shared-database backup/restore and any filtered tenant export/restore are tested without cross-container damage.
- Automated tests cover isolation, sharing, roles, key workflows, and migration paths; deployment/configuration/backup instructions are documented.

## 5. Confirmed requirements and pending decisions

- **Frontend/deployment:** Pure Flask/Jinja with local CSS and vanilla JavaScript/HTMX; one authoritative shared office/local-network server or cloud host; no Node runtime/build dependency. Confirm server OS, LAN access, HTTPS/TLS and backup placement during deployment.
- **SaaS tenancy (confirmed):** One shared MySQL database for the platform. Each independent customer/business has a separate logical tenant container; a customer can add child companies and branches inside its existing container. Even a one-branch/one-staff customer gets its own container. “Container” is a logical tenant boundary, not a Docker runtime container.
- **Data synchronization (confirmed direction):** Authorized users inside a container share canonical data according to domain policies and role permissions. The implementation currently seeds conservative company-level sharing for each domain; whether production should default to container-wide sharing and which roles may change high-impact policies remains open in [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md).
- **Roles/workflows:** Main Admin/Super Admin → Tenant/Company Admin/Sub Admin → managers → sales/cashiers. Super Admin controls the manager cross-store open-bill policy. Phone-only bill lookup is container-scoped; unpaid bills remain open until settled. Removals/cancellations require manager approval and audit. Daily manager “return/as per collection” means cash/bank end-of-day closeout.
- **Billing:** Cash, Bank and Bank Transfer have separate series; mixed-tender classification is administrator-configured. The series scope and final-number allocation timing remain undecided.
- **Current database:** `Node Js Version/netpos.db` is sample data, not production data. Do not treat its records as a production upload.
- **Automatic backups:** An administrator-configurable scheduler writes private MySQL dump files under `Flask Version/backup/` by default. Keep backups persistent/private and replicate off-host for disaster recovery. The future tenant model remains in one physical database.
- **Still to decide before schema freeze:** Invoice series scope/timing; which admin roles may change container-wide domain-sharing settings; whether child companies have their own delegated admins; and whether one staff login may be explicitly a member of multiple independent containers. The architecture document lists these questions and acceptance tests.

**Current work status:** Documentation was completed before implementation, and the user subsequently authorized phases. The active branch now contains the `ba2fd4c7e8a1` tenant-container migration, per-company backfill, nested companies, memberships, policy/action checks, Main Admin-only policy editing with audit history, and scoped importer/sales records. The approved default is company-level sharing; only Main Admin can change policies. Local tests and migration checks pass, but all-module enforcement, live MySQL, restore, staging and production acceptance remain open. The current phase is still tenant-container foundation completion; the next business-module phase has not begun.
