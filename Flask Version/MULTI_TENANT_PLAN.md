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

The working tree contains tenant-container, importer, sales/billing, catalog/inventory and realtime slices. Phase 0/1 are complete and Phase 2's isolated SQLite checks pass; **Phase 3 is active but incomplete**. The app remains intended for MySQL, and the user will run live MySQL/staging/reconciliation/restore/media acceptance locally later in Phase 6. These checks are not claimed as passed. Phase 4 remains paused until Phase 3 is accepted. The actual two-browser office/MySQL check is also a Phase 6 gate. The current implementation is not production-ready SaaS.

## Architecture and build order

0. **Phase 0 is closed.** The role/workflow inventory and release target, conservative tenant-admin and staff-membership defaults, per-company three-series billing scope, order-creation number allocation, sample-data boundary, and external production gates are recorded.
1. **Phase 1 is complete locally.** Authentication, account lifecycle, permissions, health/security and independent session tests pass. The actual shared-office/two-browser check is retained for Phase 6 deployment acceptance.
2. **Phase 2 local verification is complete.** 36 focused and 114 total tests pass on isolated SQLite, with fresh SQLite migrations/schema checks and offline MySQL DDL generation. Live MySQL, staging/reconciliation, real backup/restore, and real-media acceptance remain pending for the user's local MySQL run in Phase 6.
3. **Phase 3 is active and incomplete.** POS/catalog work allocates stable company order references at creation, prices from the authorized catalog, deducts stock with audited movements on sale/add, restores stock after approved removal, supports barcode lookup and bounded CSV import/export, and transfers inventory atomically between authorized stores of one company. Manager/admin settled-order returns and tendered refunds are recorded idempotently with stock restoration and cashup netting. Initial company/store-scoped demand notices and quotations now have audit/status workflows and stock-backed conversion of eligible catalog-linked documents into open bills. Deposits/partial fulfillment, exchanges/credit, tax/discount and return printing, receiving/purchasing integration, category administration, barcode/label printing, and the remaining business modules are open.
4. **Phase 4 is paused.** The partial inventory realtime slice exists from prior out-of-order work; continue other events, multi-worker fan-out, retention, and offline/idempotent conflict behavior only after Phase 3 acceptance.
5. **Phase 5 has not started.** Complete role-specific Flask UI and remaining feature/printing parity only after Phase 4 acceptance.
6. **Phase 6 has not started.** Run full MySQL/staging, migration, restore, concurrency, multi-session, and pilot acceptance only after Phase 5 acceptance.

Preserve prior local work without treating it as phase acceptance. Phase 3 proceeds after the locally verified Phase 2 implementation; do not treat that as MySQL sign-off. Keep Phase 4 paused until Phase 3 acceptance, and retain the live MySQL/staging/restore/media and two-browser checks as Phase 6 gates.

Keep `Node Js Version/` unchanged until parity and migration are approved. Do not treat the checked-in SQLite sample as production data.
