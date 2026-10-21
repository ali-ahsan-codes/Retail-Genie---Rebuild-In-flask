# Retail Genie: Flask + MySQL Migration Plan

**Status:** Phase 0 scope baseline, local Phase 1 foundation, Phase 2 local verification, Phase 3 implementation, **Phase 4 realtime/offline implementation**, and **Phase 5 UI parity implementation plus local verification are complete**. Phase 6's local readiness work is in progress, with live acceptance gates still pending. **Phase 7 SaaS productization is implemented and locally verified** (tenant plans/subscriptions, usage limits, plan requests, manual OMR subscription invoicing, and customer administration). SQLite is used only for isolated tests and migration/schema checks; the Flask runtime remains configured for MySQL. No live MySQL/staging reconciliation, real backup/restore, approved-media migration, office-network/two-browser, or true MySQL concurrency checks have passed.

**Remaining work:** Phase 7's full local all-phase suite passed **157 tests, 1 skipped**, and SQLite migration upgrade/check/explicit downgrade/re-upgrade/check passed. The skipped test requires a migrated disposable MySQL test database; no live MySQL validation was performed. Phase 6 live MySQL/importer reconciliation, real backup/restore, approved media migration, office-network/two-browser checks, and true MySQL concurrency remain separate external gates. Do not claim staging, production-data, restore, or live-MySQL success from local tests or offline DDL.

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
- [x] Validate independent client sessions against the shared local app database. At Phase 1 closure, its focused suite passed 26 tests and the full suite had 90; later Phase 2/3 work has expanded the current full suite to 135 tests.
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

**Status:** Phase 3 business workflows are implemented and locally verified. This includes company/store-scoped catalog/categories/barcodes/labels; import/export/transfers and inventory ledger; POS, open bills, exchanges/store credit, discounts/tax, tender settlement, returns/refunds/cashup, order register/fulfillment and print views; commercial quotations and demand notices with editing, deposits, partial fulfillment, print/email, conversion and audit history; SCM suppliers, purchase orders, receiving, attachments and logistics; attendance/breaks; stock audits and private evidence; messaging and protected attachments; private cloud files; sales/activity reports; LCD display; and role-aware admin settings/navigation. Money and inventory changes are transactionally scoped, permission/domain/store checks remain enforced, and business changes retain audit history. The full local regression suite passes **135 tests**, with a fresh SQLite migration/schema check and downgrade/re-upgrade cycle passing. These are local checks only; no live MySQL, staging, restore, production-data, real-media, or deployment acceptance is claimed.

- [x] Catalog/category/barcode/label, inventory, CSV import/export, store transfers, receiving integration, audit history and policy/store isolation.
- [x] Sales: POS/open bills, payments and tender series, discounts/tax, exchanges/store credit, returns/refunds, cashup, fulfillment, order register, receipt and return-slip print routes.
- [x] Commercial: quotations/demand notices, document edits, deposits, partial fulfillment, conversion, print/email, authorization and audit history. Email uses opt-in SMTP settings and fails closed when mail is not configured.
- [x] SCM: suppliers, products, purchase orders, receiving, protected attachments, draft edits and logistics tracking.
- [x] Attendance/breaks/selfie access, stock audits/evidence, messaging/files, reports/exports, LCD display, and remaining role-aware settings/admin links.
- [ ] Live MySQL/staging, backup/restore, approved production media, and office-network/two-browser acceptance remain external deployment gates (Phase 6); they are not prerequisites falsely implied by SQLite results.

For every module, port the rules and permissions, not just the visible page. Use MySQL transactions for inventory and money-changing actions.

### Phase 4 — Real-time and offline behavior (implementation and local verification complete)

**Status:** Phase 4 is implemented locally. The generalized durable event outbox now covers inventory/stock changes, sales/order/payment/return/cashup changes, receiving, and access-policy/membership/assignment invalidations. Authenticated Socket.IO fanout is reauthorized against current tenant, domain, role, company, and store scope. A DB-polling dispatcher fans events to each worker's local sockets, with a bounded overlap scan for late commits; cursor replay spans authorized sales and inventory domains and returns an explicit expired-cursor response using retention watermarks. The Products & Inventory screen reconnects/replays and queues only stock adjustments in IndexedDB, using tenant/user-scoped idempotency keys; conflicting or newly unauthorized queued operations are blocked for review. Checkout/payment are not queued offline. The full local suite passes **142 tests**, and fresh SQLite migration/schema checks plus an offline MySQL DDL render pass. These do not constitute live MySQL/staging or production sign-off.

- [x] Persist inventory and business events in the same transaction as stock/order/payment/return/receiving changes, and publish only after commit.
- [x] Add authenticated store subscribe/unsubscribe, per-event authorization rechecks, and durable recipient-only access-change events for policy, membership, assignment, password/auth-version, and deactivation changes.
- [x] Add authenticated cross-domain replay, client reconnect/replay, explicit retention floors/cursor expiry, and browser connection/update status.
- [x] Add multi-worker DB-outbox polling, local per-worker deduplication, and retention pruning that preserves scope-specific replay anchors.
- [x] Add IndexedDB queueing and actor-scoped idempotency for stock adjustments; identical retries reuse the original movement, while key/payload conflicts and revoked access are surfaced instead of silently applied.
- [x] Add local regression tests for domain replay, cursor expiry/retention, independent worker registries, late-commit overlap, recipient-only access revocation, and stock retry idempotency.
- [ ] Run true simultaneous sales, receiving, and stock changes against approved MySQL with separate sessions/workers; this remains an external MySQL acceptance check because no live MySQL server is reachable in this workspace.

Offline financial actions remain online-only by design; do not queue checkout/payment. No client may overwrite stock silently: the server applies deltas transactionally and rejects insufficient-stock or idempotency conflicts.

### Phase 5 — UI migration and feature parity (implementation and local verification complete)

**Status:** Shared Flask/Jinja layouts, responsive role-aware navigation and dashboards, form/table workflows, validation, and printing surfaces have been completed in the existing Flask UI. The role dashboards now present actions based on current permissions and tenant/company context. Sales, express checkout, catalog/inventory, commercial, SCM, attendance, stock audit, messaging/files, reports, settings/admin, and LCD workflows are presented through the shared shell. Printed receipts, return slips, quotations, and demand notices now include bilingual English/Arabic labels; OMR output remains three-decimal. POS and express checkout support keyboard-wedge barcode scans; Code 39 product/document label printing and 80 mm thermal receipts are retained. The legacy Node application remains untouched as the comparison/reference. Phase 5 closed with **145 passing tests**; Phase 6 adds local preflight coverage. These are local UI/API checks, not browser matrix, live MySQL, or production parity sign-off.

- [x] Build the shared Flask layout and a responsive collapsible navigation that shows links according to active role/permissions.
- [x] Replace the phase roadmap placeholder with role-aware dashboards and authorized module shortcuts.
- [x] Complete responsive forms, tables, validation, barcode/SKU scan flows, labels, bilingual print views, OMR precision, thermal receipt styling, and LCD display checks.
- [x] Keep `Node Js Version/` available unchanged; no Node runtime or build is introduced.
- [ ] Live office-browser, device/printer matrix, MySQL/staging, and production workflow parity acceptance remain Phase 6 gates.

### Phase 6 — Verification, pilot, and cutover (in progress; external acceptance blocked pending staging access)

See [`PHASE_6_ACCEPTANCE.md`](PHASE_6_ACCEPTANCE.md) for the gated runbook and evidence log. A read-only `flask --app wsgi phase6-preflight` command now checks MySQL 8, Alembic head parity, mapped tables/InnoDB, and foreign-key enforcement. It rejects SQLite before issuing SQL; it performs no writes.

- [x] Re-run the complete local suite and isolated SQLite migration cycle as engineering checks; neither is live MySQL acceptance.
- [x] Add the preflight guard and verify it refuses the local SQLite target without executing MySQL queries.
- [ ] Run the preflight and reviewed Alembic migration path on an approved disposable MySQL staging database; retain sanitized evidence.
- [ ] Verify two separate browsers on the shared office/local-network server against one central MySQL database: LAN routing, TLS, session isolation, sharing, permissions, and reconnect/replay.
- [ ] Test real MySQL backup and restore into a separate disposable database; verify schema, row/financial/stock totals, and private media.
- [ ] Run true MySQL concurrency tests for checkout, payment, returns, receiving, and stock changes, plus real large uploads, duplicate retries, network interruption, and active-session permission revocation.
- [ ] Pilot only with approved copied data and a small user group; reconcile old/new counts and reports.
- [ ] Cut over only after explicit approval and a final verified backup. Preserve rollback; do not retire Node until feature parity and data reconciliation are signed off.

No MySQL server/client, approved staging URL/data, office network, or real printer/scanner set is available in this workspace. Those checks remain pending; Phase 6 is not complete and no production cutover has been performed.

### Phase 7 — SaaS productization (implementation and local verification complete; live MySQL pending)

See [`PHASE_7_SAAS.md`](PHASE_7_SAAS.md) for the selected feature scope and acceptance checklist. Implemented locally so far: Main Admin-controlled plan catalog and tenant subscriptions; OMR prices and tenant-scoped usage/quota checks for companies, stores, and active users; tenant plan-change requests with Main Admin review; manually issued OMR subscription invoices and manually recorded external payment references; platform audit events; tenant subscription portal/print view; and read-only write blocking for suspended/canceled subscriptions. Tenants without a subscription remain grandfathered/unmetered. No public registration, payment gateway, recurring-charge automation, or production data changes are introduced.

The Phase 7 Alembic revision was generated against a temporary SQLite database upgraded to the previous migration head, then reviewed. The full local suite passes **157 tests, 1 skipped**; the skipped Phase 6 test requires a migrated disposable MySQL database. The complete SQLite migration chain upgrades, `db check` passes, downgrade to `f4c1b7a2d903` and re-upgrade to Phase 7 head pass, and a final `db check` reports no model drift. This does not establish live MySQL migration compatibility or any Phase 6 staging/deployment acceptance.

- [x] Implement the local SaaS models, routes, templates, services, quota hooks, audit records, customer administration, and tests.
- [x] Review the generated migration and update the Phase 7/README/architecture documentation.
- [x] Run the requested combined all-phase local test suite and SQLite migration upgrade/check/downgrade/re-upgrade checks after development completion.
- [ ] Keep Phase 6 live deployment gates independent; no staging, restore, pilot, or cutover is authorized or implied by Phase 7 local work.

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
- **SaaS productization (Phase 7 locally complete):** Main Admin-controlled plan/subscription assignment, company/store/active-user quotas, tenant plan requests with Main Admin review, and manually issued/reconciled OMR subscription invoices are implemented and locally verified. Existing unassigned tenants remain unmetered; onboarding remains private/admin-provisioned. No payment gateway or public registration is assumed. Live MySQL integration and Phase 6 deployment gates remain pending.
- **Current database:** `Node Js Version/netpos.db` is sample data, not production data. Do not treat its records as a production upload.
- **Automatic backups:** An administrator-configurable scheduler writes private MySQL dump files under `Flask Version/backup/` by default. Keep backups persistent/private and replicate off-host for disaster recovery. The future tenant model remains in one physical database.
- **Remaining decisions before schema freeze:** whether child companies have their own delegated admins and whether one staff login may be explicitly a member of multiple independent containers. Company-level defaults, company-scoped billing series, order-reference creation timing, and Main Admin-only policy authority are recorded.

**Current work status:** Phase 0, local Phase 1/2 verification, Phase 3, Phase 4, Phase 5, and Phase 7 local implementation/verification are complete. The combined suite passes 157 tests with 1 opt-in MySQL test skipped; the full SQLite migration cycle passes. Phase 6 readiness/preflight work is in progress and its live acceptance gates remain pending. The two-browser office/MySQL check, live MySQL/staging reconciliation, restore, real-media checks, device/printer matrix, and true MySQL concurrency tests remain separate Phase 6 deployment gates. SQLite results and offline MySQL DDL are local engineering evidence, not production or live-MySQL sign-off.
