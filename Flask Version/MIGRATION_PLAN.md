# Retail Genie: Flask + MySQL Migration Plan

**Status:** Phase 1 foundation is implemented; business modules and real-time data events remain to be migrated. Automated tests currently use an isolated test database; a live office MySQL server has not been configured in this workspace.

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

- Use **one central MySQL 8 / InnoDB database as the source of truth**. All user accounts and all cashier, sales, inventory, audit, SCM, and other clients connect to the same Flask server; browser clients never connect directly to MySQL.
- Use SQLAlchemy 2.x and Alembic/Flask-Migrate. Store OMR money as `DECIMAL` (not floating-point), preserve stable existing IDs and document-number series, add foreign keys/indexes, and normalize important transactional data such as order lines and payments where that improves reporting and integrity.
- Run sales, payments, returns, stock deductions/receipts, and document-number allocation in database transactions. Add idempotency keys to operations that may be retried so an offline retry or dropped response cannot create a duplicate sale/payment.
- Add authenticated real-time events using Flask-SocketIO (or an equivalent WebSocket/SSE design). After a database transaction commits, emit a minimal event to the correct authorized users/store, then let the UI update or fetch the changed record. Persist event/outbox rows with the transaction so a process restart does not silently lose notifications.
- Reconnect with a last-seen event cursor and fetch missed changes. Keep a slower polling/revalidation fallback for disconnected clients. If the production deployment runs multiple Socket.IO workers, use Redis only as the event fan-out/message queue; **MySQL remains the business-data database**.
- “All accounts sync” means every account sees authorized changes from the same central database. It does not mean sending passwords or sessions between accounts. Role and permission changes should take effect server-side and invalidate or refresh affected sessions.

### Authentication, files, and operations

- Add a Flask login/logout flow with Argon2id password hashes, signed `HttpOnly`/`Secure`/`SameSite` cookies, CSRF protection, login rate limits, and server-side role/permission decorators. Keep only the user ID and a revocable authentication-version marker in the signed session; reload role, permissions, and account status from MySQL. Do not trust `X-User-ID` for authentication.
- Use environment-based secrets/configuration. Do not ship default production credentials or commit `.env` files.
- Initially keep uploaded media in a configured persistent `UPLOADS_DIR`, with MySQL storing metadata and relative paths. Apply file-size/type validation and authorization checks to downloads. Back up uploads with the database; object storage can be added later if needed.
- Use a single authoritative deployment (an office server reachable by all devices, or a cloud VPS). Installing a separate Flask + MySQL database on every client would recreate the current data-isolation problem.

## 3. Phased development plan

### Phase 0 — Confirm scope and protect existing data

- Confirm whether the checked-in SQLite snapshot is demo data or the source to migrate.
- Identify the real SQLite database and all upload/media folders; create a verified, restorable backup before any conversion.
- Confirm whether “remove Node.js” means no Node at runtime **and** no Node build dependency. The recommended plan assumes both are removed.
- Confirm the first deployment target: a shared local-office server or a cloud server.
- Build a role-by-role workflow inventory from the existing pages and API routes; agree which features are must-have for the first usable release.

### Phase 1 — Flask foundation

- [x] Add the Flask app factory, environment configuration, request security headers, health/readiness checks, Python dependency file, and setup/run instructions inside `Flask Version/`.
- [x] Add SQLAlchemy, an initial Alembic migration, MySQL URL configuration, CSRF protection, revocable signed sessions, and a pytest suite.
- [x] Implement Argon2id login/logout, safe current-user lookup, server-side permission decorators, first-admin provisioning, and account create/activate/deactivate workflows.
- [ ] Verify two separate browsers against the same central office MySQL instance. This requires the office MySQL server/network configuration, which is not available in this workspace yet.

### Phase 2 — MySQL schema and safe data import

- Map the 27 SQLite tables and their JSON/text fields into a documented MySQL schema. Preserve foreign-key relationships, existing IDs, invoice/quotation/PO/audit sequences, and historical timestamps.
- Write a **dry-run, repeatable importer** from SQLite to MySQL. Hash legacy passwords during import, remove/reset any demo/default credentials, and avoid logging password values.
- Validate table counts, foreign keys, order totals, payment totals, stock totals, and document-number counters. Run the importer on a backup first and rehearse rollback before cutover.
- Migrate uploaded files separately and verify every database path resolves to a real file.

### Phase 3 — Port business modules in dependency order

1. Users, sessions, roles, permissions, settings, and activity/audit logging.
2. Products, categories, search/barcode lookup, stock, and CSV import/export.
3. Orders, checkout, payments, invoice numbering, returns/exchanges, and receipt printing.
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
- All authorized devices use one MySQL source of truth; a change made by one user reaches authorized connected clients in near real time, with reconnect/replay fallback.
- Existing required roles and workflows are covered, including sales, inventory, finance, accounts, audits, SCM, messaging/files, reports, and printing.
- Passwords are never returned by an API, stored in plaintext, or used as client-side authentication; every protected operation is checked server-side.
- Concurrent checkout, returns, and stock receiving preserve correct totals and stock; retrying the same request does not duplicate a financial operation.
- The SQLite-to-MySQL importer is repeatable and its reconciliation report matches the approved source data; upload backups and database restore have been tested.
- Automated tests cover the critical workflows, and deployment/configuration/backup instructions are documented.

## 5. Confirmed planning decisions

- **Frontend:** Follow the strict no-Node path. Rebuild the UI in Flask/Jinja with HTMX and/or vanilla JavaScript; the delivered app must not need Node or npm to run or build.
- **Deployment:** Use one shared office/local-network server as the source of truth for all devices. Confirm the server OS, LAN access, HTTPS/TLS, and backup location during deployment planning.
- **Current database:** The checked-in `Node Js Version/netpos.db` is demo/sample data, not the production dataset. Use it only for development and migration tests. If real production data or uploads are found later, back them up and assess them separately before importing.

The first development milestone should therefore be the Flask foundation, secure MySQL configuration, and a local office-server deployment runbook. Keep the Node version unchanged until feature parity and the final data checks are approved.
