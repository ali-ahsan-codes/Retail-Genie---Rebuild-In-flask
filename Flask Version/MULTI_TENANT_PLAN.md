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

The working tree now has the tenant-container foundation on the active branch: `tenant_container_id` is separate from company identity; each pre-existing company is backfilled into its own container; new child companies can be nested in a selected container; memberships and explicit action grants are used for tenant context; and the policy engine supports company, container, assigned-store, selected-unit, and disabled modes. Sales/billing and legacy-import records are container-scoped. The focused foundation tests and full suite currently pass (75 tests), and migration tests cover two-company backfill. This remains an implementation draft, not production-ready SaaS: live MySQL, policy-admin screens/audit history, all-module/page/export/file/realtime enforcement, backup restore, staging, and deployment checks remain outstanding. Do not push it as complete or advance to the next business-module phase until the current foundation gates are accepted.

## Architecture and build order

1. Finish and accept the current tenant-container foundation: fresh migration/backfill, foreign-key/offline checks, cross-container and policy/action tests, and a review of remaining policy defaults/delegation.
2. Complete policy-administration screens/audit and broader request coverage, then validate on live MySQL and rehearse backup restore before production use.
3. Only after those gates, build container/domain/action-scoped product catalog and inventory; follow with customers and remaining retail modules.
4. Add permission-scoped realtime updates and the remaining UI/feature parity.
5. Run full MySQL/staging, migration, restore, concurrency and multi-session acceptance before cutover.

Keep `Node Js Version/` unchanged until parity and migration are approved. Do not treat the checked-in SQLite sample as production data.
