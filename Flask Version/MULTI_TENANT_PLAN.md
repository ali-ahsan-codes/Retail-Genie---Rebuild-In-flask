# SaaS tenant-container requirements

**Status:** The user has confirmed a SaaS product with one shared MySQL database and one logical data container per independent customer/business. This file is a short requirements index; the detailed architecture, data model, policy, lifecycle, open decisions and acceptance tests are in [`SAAS_TENANCY_ARCHITECTURE.md`](SAAS_TENANCY_ARCHITECTURE.md).

## Confirmed model

- One physical/shared MySQL database serves the whole Retail Genie platform.
- Every independent customer/business receives a separate **logical tenant container**, even when it has only one branch and one staff member. “Container” is a data-isolation concept, not a Docker container.
- One tenant container can contain a parent company, child companies and branches/stores. A new child company/branch that belongs to an existing customer can be added to that container later.
- Data is shared within the same container according to the configured data-domain sharing policy and user roles. In normal operation, the user's “sync” means authorized accounts read and change the same canonical records; data is not duplicated into a separate database for each branch.
- No customer, order, product, inventory, account, file, report, audit or realtime event may cross the tenant-container boundary.
- Main Admin/Super Admin provisions containers and controls platform-level structure. Tenant/company admins, managers and sales/cashiers receive explicit memberships, roles and company/branch assignments.
- Data-domain settings must be able to enable/narrow/disable sharing inside a container (e.g. inventory, customer records, orders, roles/accounts). Role permissions independently govern view/add/edit/delete/approve actions; neither policy nor role alone bypasses the other.
- Existing retail requirements continue to apply: phone-only company/container-scoped open-bill lookup, unpaid bills stay open until settled or formally voided, audited manager-approved removals/cancellations, separate Cash/Bank/Bank Transfer billing series, admin-configured mixed-tender classification, audited daily cash/bank closeout, scheduled backups in the app's `backup/` directory, and authorized real-time updates.

## Current code status

The working tree contains tenant-container, importer, business-module, Phase 4 realtime/offline code, and Phase 5 UI parity work. Phase 0–5 local implementation checks pass; live MySQL/staging/reconciliation/restore/media acceptance remains pending in the user's environment. These external checks are not claimed as passed. Phase 6 pilot/cutover has not started. The actual two-browser office/MySQL check is also a deployment gate. The current implementation is not production-ready SaaS.

## Architecture and build order

0. **Phase 0 is closed.** The role/workflow inventory and release target, conservative tenant-admin and staff-membership defaults, per-company three-series billing scope, order-creation number allocation, sample-data boundary, and external production gates are recorded.
1. **Phase 1 is complete locally.** Authentication, account lifecycle, permissions, health/security and independent session tests pass. The actual shared-office/two-browser check is retained for Phase 6 deployment acceptance.
2. **Phase 2 local verification is complete.** 36 focused and 114 total tests pass on isolated SQLite, with fresh SQLite migrations/schema checks and offline MySQL DDL generation. Live MySQL, staging/reconciliation, real backup/restore, and real-media acceptance remain pending for the user's local MySQL run in Phase 6.
3. **Phase 3 implementation and local tests are complete.** The Flask app covers the scoped catalog, inventory, sales, commercial, SCM, attendance, audit, messaging, file, report, display, and admin workflows described above. Phase 3 closed with 135 tests; the current full suite passes 145 tests after Phase 4 and Phase 5 coverage. Isolated SQLite migration/schema checks pass. Live MySQL, staging, restore, media, concurrency, and office-network deployment checks remain unverified and are not implied.
4. **Phase 4 implementation and local verification are complete.** Durable event coverage, access invalidation, multi-worker polling, retention/replay, stock-adjustment offline queueing, and idempotency tests are implemented; true MySQL concurrency remains an external acceptance check.
5. **Phase 5 implementation and local verification are complete.** The responsive shared shell, permission-aware navigation, role dashboards, bilingual print views, POS/Express barcode scan flows, OMR precision, thermal receipts, labels, and LCD presentation are implemented. The local full suite passes 145 tests. Real device/printer/browser matrix and workflow parity remain Phase 6 acceptance gates.
6. **Phase 6 has not started.** Run full MySQL/staging, migration, restore, concurrency, multi-session, and pilot acceptance only after Phase 5 acceptance.

Phase 4/5 local implementation and test acceptance is complete; do not treat it as MySQL/deployment sign-off. Keep Phase 6 live MySQL/staging/restore/media, concurrency, and two-browser checks as external deployment gates.

Keep `Node Js Version/` unchanged until parity and migration are approved. Do not treat the checked-in SQLite sample as production data.
