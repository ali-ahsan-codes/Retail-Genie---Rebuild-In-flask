# Retail Genie: Flask + MySQL Migration Plan

**Status:** Phase 0 is closed and the local Phase 1 foundation is complete. The Phase 2 implementation has passed its SQLite-backed local checks, and **Phase 3 is active** under the user's latest direction: SQLite may be used for isolated local verification, while the application runtime/configuration remains MySQL. The user will run the live MySQL checks locally later. Phase 2's MySQL/staging, real restore, and real-media gates remain pending and are not represented as passed; they no longer block Phase 3 implementation. Phase 3 is still broad, incomplete, and unaccepted. Phase 4 remains paused. The two-browser office/MySQL test remains a Phase 6 deployment gate. No local result is production sign-off.

**Remaining work:** Continue Phase 3 business workflows and tests. Keep `DATABASE_URL` aimed at MySQL for actual app use; SQLite is for isolated tests/migration checks only. Defer the user's live MySQL/importer reconciliation, real backup/restore, approved media migration, and office-network checks to their explicit later acceptance gates. Do not claim MySQL staging, production-data, restore, or real-media success from local SQLite tests or offline DDL.

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

### Phase 0 — Confirm scope and protect existing data (closed as a safe-development baseline)

- [x] Confirm the checked-in `Node Js Version/netpos.db` is demo/sample data only; do not treat it as the production dataset.
- [x] Record that no production database or `uploads/` directory is present in this checkout; an external source remains unidentified, so no real conversion is authorized without a verified backup.
- [x] Confirm the strict no-Node requirement: no Node runtime and no Node/npm frontend build dependency.
- [x] Confirm the deployment shape is a shared office/local-network server; record exact OS, LAN/TLS and persistent backup location as hard pre-pilot/cutover gates because they are not available yet.
- [x] Confirm a SaaS shared-database architecture with one logical tenant container per independent customer and child companies/branches inside a container.
- [x] Confirm conservative company-level sharing defaults, Main Admin-only data-domain policy authority, and that no cross-container data sharing is allowed.
- [x] Confirm that an administrator controls manager cross-store open-bill policy and that daily manager “return/as per collection” means cash/bank end-of-day closeout.
- [x] Complete the role/workflow inventory and set the full legacy workflow tree as the first-usable-release parity target in [`PHASE_0_WORKFLOW_INVENTORY.md`](PHASE_0_WORKFLOW_INVENTORY.md); no feature is dropped by this baseline.
- [x] Record conservative defaults: child-company Admin manages its own company/stores unless Main Admin explicitly delegates broader scope; normal staff are single-container by default, with any multi-container membership explicit and isolated.
- [x] Record billing defaults: three separate Cash/Bank/Bank Transfer series per legal company across its stores; allocate a stable order number at order creation to preserve legacy flow; admin configures mixed-tender classification.
- [x] Close Phase 0 at the user's direction. External production-data, live database, host and backup facts remain hard gates in the relevant later phases; no production conversion/deployment is authorized until satisfied.

### Phase 1 — Flask foundation (complete; local acceptance)

- [x] App factory, environment configuration, security headers, health/readiness checks, Python dependencies and run/setup instructions.
- [x] SQLAlchemy/Alembic foundation, MySQL URL configuration, CSRF protection, revocable signed sessions and pytest coverage.
- [x] Argon2id login/logout, safe current-user lookup, server-side permissions, first-admin provisioning, and account lifecycle.
- [x] Validate independent client sessions against the shared local app database. At Phase 1 closure, its focused suite passed 26 tests and the full suite had 90; later Phase 2/3 work has expanded the current full suite to 114 tests.
- [x] Close the local Phase 1 foundation scope. The actual two-browser test against central office MySQL/LAN is carried as a Phase 6 deployment integration gate; it has not been performed and is not production sign-off.

### Phase 2 — MySQL schema and safe data import (local SQLite verification complete; live MySQL gates pending)

The Phase 2 code has passed its local SQLite-backed suite: 36 Phase 2-focused tests and 114 total tests pass; a fresh SQLite Alembic upgrade and `flask db check` pass; and offline MySQL DDL generation succeeds. These checks validate local code/schema behavior only; they are not live-MySQL integration, staging reconciliation, real backup/restore, or approved-media validation. Per the user's updated instruction, Phase 3 may proceed while the user-run MySQL acceptance remains pending for Phase 6. The target runtime stays MySQL; SQLite is limited to isolated verification.

- [x] Map all 27 checked-in SQLite tables into a documented MySQL/InnoDB landing schema (`LEGACY_SCHEMA_MAP.md`). Preserve stable IDs, foreign-key relationships, date/time values normalized to UTC, JSON payloads, and document-number counter rows; monetary columns use `DECIMAL` rather than floating point.
- [x] Add a read-only, immutable-source dry run and insert-only transactional importer. It checks the reviewed source schema, foreign-key integrity, JSON, numeric precision, usernames, and permission mappings. A matching existing ID is skipped; a conflict rolls back the whole import rather than overwriting target data.
- [x] Reset legacy credentials to random unknown values by default and hash them with Argon2; force a password change. An explicitly confirmed option can hash vetted legacy credentials, and operators can interactively provision a temporary password for approved imported accounts. No credentials are printed or logged.
- [x] Add the requested admin-configurable automatic MySQL backup interval, dedicated single-instance scheduler/worker, private `.sql.gz` files under `Flask Version/backup/` by default, SHA-256/run history, gzip CRC/non-empty validation, and configurable file retention. Backup files are ignored by Git; the worker is not started inside web workers.
- [x] Add source-to-target row-count/ID checks, target foreign-key checks, and reconciliation of order totals, nested payment amounts, aggregate product stock, and invoice-number counters; the import transaction rolls back on mismatch.
- [x] Add `migrate-media` dry-run/apply tooling: validate the read-only SQLite source, reject traversal/symlinks, hash and preserve the complete uploads tree in a private tenant/company namespace, validate/rewrite legacy cloud manifests, transactionally rewrite imported paths, and verify target DB paths resolve. Source URLs and embedded data remain unchanged.
- [ ] Deferred to Phase 6 for the user's local MySQL environment: run the importer, media migration, reconciliation, concurrency checks, and backup restore/rollback rehearsal against approved staging MySQL; obtain independent reconciliation sign-off. No such MySQL/staging result is recorded here.
- [ ] Deferred to Phase 6: run media migration against the approved real uploads directory and verify every scoped production/staging file reference; the checked-in sample database has no referenced local upload files.

#### SaaS tenant-container foundation — implemented locally; production gates remain

- [x] Confirm one shared MySQL database and a logical tenant container per independent customer; nested companies and branches belong to a selected container.
- [x] Document the hierarchy, data-domain policy, role/branch authorization, lifecycle, migration strategy, open decisions, and acceptance criteria in [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md).
- [x] Add `tenant_containers`, nested company relationships, active container memberships, container-scoped store assignments, domain policies/scopes, and same-container composite foreign keys.
- [x] Backfill each pre-existing company into its own container so the earlier company isolation is not silently weakened; test two-company data, membership, assignment, billing-series and audit backfill with SQLite foreign-key checks.
- [x] Implement server-side active-container selection, explicit multiple-membership selection, role/store scoping, action-level domain grants, and tenant-aware importer and sales/billing queries/records.
- [x] Add cross-container API/service and in-container policy/action tests. Coverage now includes the Phase 3 product slice and an initial Phase 4 inventory event path, but not every page, export, file, report or realtime event type.
- [x] Generate offline MySQL DDL and verify the fresh SQLite Alembic chain and `flask db check` locally. A live MySQL server is not available in this workspace.
- [x] Confirm company-level sharing as the starting default and Main Admin as the only role allowed to change domain policies.
- [x] Add Main Admin-only policy index/editor, company/container/assigned-store/selected-unit/disabled modes, selected-unit allow/deny lists, policy versioning, and before/after tenant audit history.
- [ ] Enforce/verify domain scopes across every future module and invalidate subscriptions immediately when access changes. The initial inventory socket path rechecks current permissions and sharing scopes on each event, but does not yet provide explicit revocation pushes or multi-worker invalidation.
- [ ] Deferred to Phase 6/user-run MySQL acceptance: run the migration, foreign-key, importer reconciliation, backup/restore and concurrency rehearsals on approved staging MySQL; do not use the checked-in sample SQLite database as production data.
- [x] Add a read-only media preflight and tenant/company-scoped full-tree copy/path-rewrite tool with hash verification, cloud manifest handling, and target path checks; no public file route is introduced by this migration utility.
- [ ] Deferred to Phase 6: apply it to approved staging/production uploads, verify all target paths, and design/test any filtered tenant export/restore so one tenant operation cannot affect another.

### Phase 3 — Port business modules in dependency order

**Status:** Phase 3 is active but far from complete. The first catalog/sales vertical slice is implemented locally: authorized POS product selection uses server catalog prices; each bill gets a stable company-scoped order reference at creation; creating or extending an open bill deducts store stock in the same transaction with an append-only `sale` movement, audit row, and durable realtime event; an approved item removal returns the quantity to the reviewing store with its own movement/audit/event. Cash/Bank/Bank Transfer invoice numbering remains allocated on full settlement, with admin-configured mixed-tender classification. Catalog work also includes category/barcode lookup, bounded company-SKU CSV import/export with inventory visibility and write-permission checks, and atomic same-company store transfers with paired movements, audit history, and per-store realtime events. A manager/admin-only settled-order return/refund workflow records returned quantities by line with a required idempotency key, restores stock and emits audit/realtime records in one transaction, and nets tendered refunds out of daily cashups. Return pricing currently uses original line prices; exchange/credit, tax/discount treatment, receipt/return-slip printing, and broader sales parity remain open. An initial demand-notice and quotation slice now has company-scoped numbering, store/role/policy checks, audit history, notice cancellation, quotation status transitions/expiry, external-line snapshots, and idempotent conversion of eligible notices and accepted catalog-backed quotations into stock-deducting open bills at their recorded price. The UI supports a single quotation line; the API supports up to 50. Deposits, partial fulfillment, full document editing/printing/email, and richer quote-to-sales treatment remain open. SQLite-backed tests cover these local paths. This is not full sales, inventory, or Phase 3 acceptance. Barcode/label printing, category administration, receiving/purchasing, attendance, audits, messaging/files/reports, display/printing, and remaining admin workflows are still open.
1. Tenant-container-scoped users, sessions, memberships, roles, domain-sharing policies, company/branch assignments, settings, and audit logging (local foundation and Main Admin policy editor implemented; deployment and MySQL acceptance remain pending).
2. [x] Initial company-owned catalog, SKU/name/category/barcode search, tenant and action-policy authorization, store-scoped inventory balance/movement ledger, audit events, legacy import/backfill, and catalog-backed POS selection. [x] Sale deductions, manager-approved removal returns, bounded CSV import/export, and atomic same-company store transfers are tied to stock/audit/realtime history. [ ] Complete category administration, barcode/label generation and printing, receiving-linked stock, broader product parity, and remaining return workflows.
3. [x] First slice of container/company-scoped open bills, phone lookup, cross-branch continuation, payments, manager-approved removals, company order references, tender-specific invoice series, catalog stock deductions/returns, and daily cashup. [x] Manager/admin settled-order return/refunds with line-level quantity limits, idempotency, inventory restoration, audit/realtime records, tendered refund records, and cashup netting. [ ] Add exchanges/credit, full tax/discount treatment, return-slip/receipt printing, order fulfillment/demand-notice links, and broader sales parity.
4. [x] Initial tenant/store-scoped demand notices and quotations: numbered/audited documents, status/expiry handling, and stock-backed conversion of eligible catalog-linked notices and accepted quotations. [ ] Complete deposits and cashup treatment, partial fulfillment, full document editing, print/email output, and remaining conversion parity.
5. Suppliers, purchase orders, receiving, attachments, and logistics tracking.
6. Attendance, breaks, stock audits, evidence images, messaging, cloud files, and reports.
7. LCD order display, barcode/label printing, and remaining admin screens.

For every module, port the rules and permissions, not just the visible page. Use MySQL transactions for inventory and money-changing actions.

### Phase 4 — Real-time and offline behavior (partial implementation exists; paused)

**Status:** Earlier out-of-order work added a partial inventory realtime slice: durable events, authenticated Socket.IO store subscriptions, per-event current-access checks, cursor replay, and browser reconnect updates. It is not Phase 4 acceptance and must remain paused until Phases 0–3 have each been explicitly completed in order. The local subscription/fan-out registry is process-local; multi-worker fan-out, retention/compaction, other module events, and safe offline/idempotent operations remain open. The current 114-test, SQLite migration/schema, and offline MySQL DDL results are local evidence only—not live-MySQL, staging, or production sign-off.

- [x] Persist `inventory.updated` events with stock balances/movements and audit rows; publish only after commit.
- [x] Add authenticated store subscribe/unsubscribe, current authorization recheck, and revocation on tenant switch/logout.
- [x] Add cursor replay and browser reconnect/replay for the Products & Inventory screen.
- [ ] Extend event coverage to sales, returns, receiving, policy/membership changes and other modules; design multi-worker fan-out and retention.
- [ ] Implement safe offline queuing/idempotency and conflict handling for stock and financial operations.

- Publish authenticated events only after successful commits; scope events by user role, recipient, and store as appropriate.
- Add client reconnect/replay, visible connection status, and safe handling of conflicts. Use optimistic UI only where the server can confirm or reject the operation cleanly.
- Keep offline queuing limited to explicitly safe, idempotent operations. A queued checkout/payment must not be replayed twice; conflicting stock changes must be reconciled rather than silently overwriting newer data.
- Test simultaneous sales, receiving, and stock changes from multiple sessions.

### Phase 5 — UI migration and feature parity (not started; wait for Phase 4 acceptance)

- Build shared Flask layouts, role-specific navigation, forms, tables, validation, and responsive dashboards.
- Recreate all required role workflows and preserve bilingual English/Arabic printing, OMR formatting, barcode scanning/labels, thermal invoices, and the LCD display.
- Keep the old Node app available as a comparison/reference until each feature has passed its acceptance checks. Do not delete it at the start of development.

### Phase 6 — Verification, pilot, and cutover (not started; wait for Phase 5 acceptance)

- Verify two separate browsers on the shared office/local-network server against the same central MySQL database; validate LAN routing, TLS, session isolation and shared canonical data. This deployment integration check was moved from the local Phase 1 foundation gate and remains outstanding.
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
- **Data synchronization (confirmed direction):** Authorized users inside a container share canonical data according to domain policies and role permissions. Every domain starts with conservative company-level sharing. Only the global Main Admin may change domain-sharing policies; role permissions and store assignments remain separate gates. See [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md).
- **Roles/workflows:** Main Admin/Super Admin → Tenant/Company Admin/Sub Admin → managers → sales/cashiers. Super Admin controls the manager cross-store open-bill policy. Phone-only bill lookup is container-scoped; unpaid bills remain open until settled. Removals/cancellations require manager approval and audit. Daily manager “return/as per collection” means cash/bank end-of-day closeout.
- **Billing:** Cash, Bank and Bank Transfer have separate invoice series per legal company across its stores; mixed-tender classification is administrator-configured. A stable order reference is allocated at order creation, while a payment-category invoice number is assigned only when the bill is fully settled.
- **Current database:** `Node Js Version/netpos.db` is sample data, not production data. Do not treat its records as a production upload.
- **Automatic backups:** An administrator-configurable scheduler writes private MySQL dump files under `Flask Version/backup/` by default. Keep backups persistent/private and replicate off-host for disaster recovery. The future tenant model remains in one physical database.
- **Remaining decisions before schema freeze:** whether child companies have their own delegated admins and whether one staff login may be explicitly a member of multiple independent containers. Company-level defaults, company-scoped billing series, order-reference creation timing, and Main Admin-only policy authority are recorded.

**Current work status:** Phase 0 and the local Phase 1 foundation are complete; Phase 2 local SQLite verification is complete, with user-run live MySQL/staging/restore/media checks explicitly pending for Phase 6. Phase 3 is active and incomplete; Phase 4 remains paused until Phase 3 is explicitly accepted. The two-browser office/MySQL check remains a Phase 6 deployment gate. SQLite results and offline MySQL DDL are local engineering evidence, not production or MySQL sign-off.
