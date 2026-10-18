# Retail Genie SaaS Tenant-Container Architecture

**Status:** Phase 0 and the local Phase 1 foundation are complete. Phase 2 implementation checks pass on isolated SQLite, while live MySQL/staging reconciliation, real restore, and approved-media validation remain pending for the user's local MySQL acceptance in Phase 6. Phase 3 is active and incomplete; local slices now cover catalog-backed sales/stock, returns/refunds, and initial demand-notice/quotation conversion workflows. Phase 4 remains paused until Phase 3 acceptance. The two-browser office-network test is also a Phase 6 gate. This document does not claim the product is SaaS-production-ready.

## 1. Confirmed product direction

- Retail Genie will be offered as a **SaaS product**.
- The platform will use **one shared MySQL database for all customers/containers**. Do not create a separate database for every customer.
- Each independent customer/business receives its own **logical tenant container**. A customer with only one branch and one staff member still has a separate container.
- A container can hold a hierarchy of child companies and branches. A new child company or branch that belongs to an existing tenant is added inside that existing container; it does not get another container by default.
- Data is shared/synchronized within a container according to the enabled data domains and the users' roles/permissions. One container must never read or change another container's business data.
- “Sync” means authorized accounts work against the same canonical database records and receive timely updates. It does **not** mean copying the same rows into separate company databases.
- Main Admin/Super Admin can provision containers and organization structure. Data-domain sharing and role permissions need to be configurable so permitted areas can later be added or removed.

> **Terminology:** “Container” here means a logical SaaS tenant/data boundary, not a Docker/Kubernetes runtime container. The physical deployment and MySQL database are shared.

## 2. Terms and hierarchy

```text
Retail Genie platform
└── Tenant Container (one independent customer/business boundary)
    ├── Company / child company / legal entity
    │   ├── Branch / store
    │   └── Branch / store
    └── Child company
        └── Branch / store
            └── users, role memberships, sales, inventory, customers, etc.
```

- **Platform:** Retail Genie SaaS control plane and one shared MySQL database.
- **Tenant Container:** The hard isolation boundary for one independent customer. Every tenant-owned business record and live event belongs to exactly one container.
- **Company / child company:** An organizational or legal entity inside a container. A container may have one company or a parent/child company hierarchy.
- **Branch / store:** A physical or operating location belonging to a company in the same container.
- **User membership:** A user's active relationship to a container and, as needed, a company or branch. Role and branch assignments apply to this membership.
- **Data domain:** A category such as inventory, customers, orders, staff/accounts, reports, or files. A container policy controls which organizational units may share that domain; role permissions control what a member may do with it.

### Examples

1. **Independent single-branch retailer:** Company “North Shop,” one branch, one cashier → create one tenant container. Its small size does not weaken the isolation boundary.
2. **Group with subsidiaries:** “Retail Group” container → parent company, two child companies, and branches under each. The authorized parts of the group can share selected domains inside this container.
3. **Another unrelated retailer:** “Harbor Store,” one branch and one employee → a different tenant container. It cannot see North Shop or Retail Group records even if the same phone number, SKU, or username exists.
4. **Later expansion:** If North Shop adds a child company or branch that belongs to its existing tenant, the Main Admin adds that organization node to North Shop's container and configures domain sharing. Do not create a second tenant unless it is an independent customer/business boundary.

## 3. Isolation and in-container sharing

### 3.1 Hard container boundary

`tenant_container_id` is the mandatory tenant key for every tenant-owned row, including companies, branches, users/memberships, products, inventory, customers, orders, payments, suppliers, uploads, reports, cashups, audit events, and realtime/outbox events.

- Container identity is resolved and authorized on the server from the signed-in membership. A browser-supplied container/company/store ID is a selector only, never proof of access.
- Every service, query, export, search, file download, report, background job, websocket room, and administrative action must enforce the same container boundary.
- Cross-container business-data reads/writes and event delivery are denied, including for guessed IDs and matching customer phone numbers.
- Main Admin platform access to tenant business records, if ever required for support, must be a separate, time-limited, explicitly audited support grant. Platform administration does not silently make tenant data public to platform users.
- Use composite foreign keys/unique keys that include the container key where applicable. A row for Container A must not reference a company, branch, user membership, order, or payment belonging to Container B.

### 3.2 Sharing within a container

The user's direction is that the container's companies and branches share their data, while the platform must support settings to add/remove sharing by domain. The implementation should therefore support:

1. **Container-wide sharing:** all eligible child companies/branches in the tenant can use the canonical data domain, subject to role and assignment checks.
2. **Narrower sharing:** a domain can be restricted to one company/subtree or selected branches without moving the records to another database.
3. **Disabled sharing:** data in that domain is not visible or writable across the restricted organizational boundary.

**Approved starting policy:** each domain is enabled with `company` sharing mode by default. This preserves company-level behavior and prevents sibling companies from silently seeing each other's data; branches/stores under one company can use that company's data subject to role and assignment checks. The user approved Main Admin as the only role that may change domain-sharing policies. The policy engine supports `container`, `company`, `assigned_store`, `selected_units`, and `disabled` modes; Main Admin changes are versioned and audit logged. Do not broaden the default or delegate policy control without an explicit product decision.

### 3.3 Policy is not the same as role permission

A request is allowed only when all required gates pass:

```text
active user + active membership
AND requested record has the same tenant_container_id
AND the data domain is enabled for the requesting and owning organization units
AND role allows the requested action (view/create/update/delete/approve/admin)
AND the user's company/branch assignment permits that record
AND business workflow rules (e.g. manager approval) are satisfied
```

Enabling inventory sharing does not grant every user permission to edit stock. Giving a role an inventory permission does not let it cross a domain-sharing boundary or a store assignment. The foundation recognizes action-specific membership permissions such as `inventory.view`, `inventory.add`, `inventory.edit`, and `inventory.delete`; existing broad application permissions remain temporarily supported for compatibility. A Main Admin-only policy screen now supports sharing modes and explicit allow/deny unit scopes, increments the policy version, and records before/after values in the tenant audit log. HTTP requests read current policy state, and the initial inventory realtime path rechecks the subscriber's current membership, role, store assignment, and relevant domain policies before each push. That process-local implementation does not yet provide cross-worker subscription invalidation or coverage for every domain.

### 3.4 Suggested domain policy matrix

| Domain | Example sharing level | Role actions to control separately |
|---|---|---|
| Product catalog | Container / company subtree / selected branches | View, create, update, archive |
| Inventory balances and movement | Container / company / branch | View, receive, transfer, adjust, audit |
| Customers and contact history | Container / company / branch | View, create, update, merge, export |
| Open bills and checkout | Container or selected companies/branches | Find by phone, continue, add item, accept tender |
| Closed sales, invoices and returns | Container / company / branch | View, issue, return, refund, export |
| Staff, accounts and role definitions | Container / company / branch | View, invite, deactivate, assign role/store, administer |
| Suppliers and purchasing | Container / company / branch | View, create PO, approve, receive, edit |
| Reports, files and messages | Container / company / branch / recipient | View, upload, download, edit, share, delete |
| Audit and daily cash/bank closeout | Container / company / branch | View, submit, approve, export |
| Company settings and billing series | Container / company / branch (policy-dependent) | View, configure, approve changes |

The policy table is data-driven and versioned rather than a collection of hard-coded UI visibility conditions. The current policy editor is restricted to Main Admin, as approved. Any later delegation or changes to available sharing modes require an explicit product decision.

## 4. Role hierarchy and administration

Requested hierarchy:

**Main Admin / Super Admin → Tenant/Container Admin → Company Admin/Sub Admin → Managers → Sales/Cashiers**

- **Main Admin / Super Admin:** Creates and disables tenant containers; creates the initial company/admin; adds child companies and branches to the correct container; grants or revokes high-impact container/domain policies and cross-branch exceptions; audits platform-level actions.
- **Tenant/Container Admin:** Administers that tenant within Main Admin policy: organization tree, domain sharing settings if delegated, company admins, account memberships, role permissions, and access reviews. Cannot access another container.
- **Company Admin/Sub Admin:** Manages the assigned company/subtree and its branches, accounts, role permissions, settings, and store assignments. Cannot expand the container boundary.
- **Manager:** Sees the branch/company scope assigned by an administrator; may approve only permitted operations in that assigned scope. Cannot grant their own access.
- **Sales/Cashier:** Performs assigned sales and payment actions. Cross-store bill continuation is controlled by the open-bill domain policy and the staff member's role/assignment; it does not automatically grant access to other reports, stock, or accounts.

Role labels and administrative delegation may differ between tenants, but every role resolves to explicit permissions and scope. Prefer container-scoped memberships and roles over relying on a single global `User.role` string. A user who is allowed to work in multiple containers must have an explicit membership and must operate under one selected container context per request/session; no automatic cross-container sharing is implied.

## 5. Organization and data model proposal

The current draft uses `company_id` as the tenant key and models a company with stores. That is insufficient for the new SaaS structure: a tenant container is not always the same thing as one legal/operating company. Before building more business modules, refactor to separate the concepts.

Suggested logical schema (names can change during review):

```text
tenant_containers
  id, slug, name, status, timezone, policy_version, created_at, updated_at

companies
  id, tenant_container_id, parent_company_id, name, legal identifiers, status

stores
  id, tenant_container_id, company_id, parent_store_id?, code, name, status

users
  id, login identifier, password hash, authentication version, status

container_memberships
  id, tenant_container_id, user_id, company_id?, store_id?, status

roles / role_permissions
  id, tenant_container_id, name, scope, permission, action

container_data_policies
  tenant_container_id, domain, sharing_mode, allowed company/store scope,
  allowed actions or related policy, version, changed_by, changed_at

tenant-owned business tables
  id, tenant_container_id, owning company_id?, owning store_id?, ...

audit_events / outbox_events
  id, tenant_container_id, actor/membership, entity, action, before/after,
  timestamp, delivery state/cursor
```

Implementation requirements:

- Add a non-null container key to all tenant-owned business rows. Keep company and store keys as additional ownership/scope dimensions; do not overload them to stand for the container.
- Use composite constraints such as `(tenant_container_id, company_id)` and `(tenant_container_id, store_id)` so foreign keys cannot cross containers.
- Define whether a customer/product is stored once at container level or has a canonical master record plus company/store-specific attributes. Do not duplicate master data solely to simulate synchronization.
- Use one canonical row per shared entity and record changes once. Scope queries and events by container and the policy-selected company/branch scope.
- A user's authorization should derive from membership + role permission + domain policy + organization/store assignment. Increment an auth/policy version and refresh or revoke active sessions/subscriptions when access changes.

## 6. What “sync” means in the shared database

All containers use the same MySQL server/database, but their data is logically isolated by `tenant_container_id`. Within a container, authorized users access the same records. The application does not copy a product/customer/order to each branch to make it “sync.”

For near-real-time screens:

1. Validate tenant membership, domain sharing, role actions, and branch scope on the server.
2. Commit the business transaction to MySQL.
3. Persist an outbox event in the same transaction where practical.
4. After commit, notify only the matching container/company/branch/user rooms.
5. Send a minimal event ID/type; clients fetch the record through the same authorized API.
6. On reconnect, fetch missed changes using a cursor; keep a safe polling/revalidation fallback.

A shared container event may reach multiple branches only when the event's domain is enabled and each recipient has a qualifying membership/permission. No event room or reconnect cursor may omit the container filter. Do not broadcast tenant data globally.

## 7. Required retail workflows inside the container

- **Phone-only open-bill lookup:** Search by normalized phone inside the active container only. If open-bill sharing is container-wide, authorized employees at any child company/branch can find and continue the bill; if narrowed, enforce the configured company/branch scope. An unpaid bill remains open across dates until settled or formally voided.
- **Cross-branch bill continuation:** Keep origin company/store distinct from the acting company/store for item additions and payments. Record actor, method, amount, location, timestamp and audit details.
- **Removals/cancellations:** Require an authorized manager approval, reason and before/after audit. Do not hard-delete financial records. A refund/credit path is required if an approved removal would make payments exceed the new total.
- **Manager closeout:** Daily manager “return/as per collection” means a cash/bank end-of-day closeout, with calculated expected amounts and administrator review.
- **Billing numbers:** Keep separate Cash, Bank and Bank Transfer invoice series per legal company across its stores, with an administrator-configured mixed-tender classification. Allocate a stable order reference at creation; allocate the tender-specific invoice number only when the bill is fully settled. These are distinct identifiers.
- **Backups:** Keep the user's app-directory `backup/` dump requirement and configurable schedule. A full shared database backup covers all tenants; any tenant-only export/restore must filter by the container key, be separately audited, and be tested to ensure it cannot overwrite another tenant.

## 8. Tenant lifecycle

### Provision an independent customer

1. Main Admin creates a tenant container.
2. Create the initial company/legal entity and first branch inside it.
3. Create the first Tenant/Company Admin membership and require a password change when using a temporary password.
4. Apply the reviewed domain-sharing defaults and role template; record a provisioning audit event.
5. No database or schema is created per tenant; the tenant is a logical scope in the shared database.

### Add a child company or branch

1. An authorized admin selects the existing container and creates a child company or branch in its organization tree.
2. Validate the selected parent is in the same container; reject any cross-container parent or assignment.
3. Choose the permitted sharing policy for each data domain and the user/role/store scope.
4. Add users by membership and grant only required roles/permissions.
5. Record organization, policy and account changes in the container audit log.

### Create another independent customer

Always create a new tenant container—even if the business has only one shop/staff member. Similar names, phone numbers, products or legal entities must not auto-merge containers. Moving an existing company between containers is a privileged data migration, not an ordinary tree edit.

## 9. Security and acceptance tests

Before rollout, test at minimum:

1. Two independent containers contain the same phone number, SKU and username; each tenant's API and UI returns only its own rows.
2. A customer with one branch and one employee gets an independent container and cannot enumerate another container's IDs.
3. A Main Admin adds a child company/branch to Container A; its configured enabled domains share data with A's authorized members, while Container B remains isolated.
4. Disable customer or inventory sharing for one company/branch; API, search, exports, downloads, reports and events all respect the restriction.
5. Enable a domain but remove a role action; the user cannot perform that action. Grant a role action but disable the domain; the request remains denied.
6. A branch manager cannot expand their own scope or see unassigned branches; manager approvals are restricted to configured supervision scope.
7. A user explicitly assigned to two containers must select an active container and cannot mix the two in one query, event subscription or session context.
8. Policy, membership, role, assignment and privileged support changes are auditable and take effect on active sessions/websocket subscriptions.
9. A container-level export/restore is filtered and cannot alter another container. Full database backup/restore still reconciles every container.
10. Concurrent order creation and settlement allocate distinct, unique order references and tender-specific invoice numbers through their company-level locked series; retries never consume the same number twice.

## 10. Confirmed policy decisions and remaining questions

The user has confirmed the starting domain-sharing policy and authority for this foundation:

- Each domain starts enabled with `company` sharing mode. Broader sharing between child companies requires an explicit setting.
- Only Main Admin may change sharing mode, enable/disable a domain, or edit selected-unit allow/deny scopes. Changes are versioned and audit logged.

Phase 0 records these conservative baselines; revisiting them requires an explicit user decision before the affected implementation is accepted:

1. **Invoice series scope:** per legal company, shared across its stores; Cash, Bank and Bank Transfer each have a distinct series.
2. **Number timing:** allocate the stable order reference at order creation, matching the reference flow; allocate the Cash/Bank/Bank Transfer invoice number on full settlement from the recorded tender(s). Unpaid bills remain open/unpaid until cleared; mixed-tender classification remains admin-configured.
3. **Child-company role boundary:** Company Admin manages only their own company and stores by default. Main Admin may explicitly delegate broader scope; no self-expansion or implicit child/sibling access.
4. **Multi-container staff:** one container membership per normal staff account by default. An exception requires explicit Main Admin-granted memberships and active-container selection; the business data remains isolated and no cross-container query is permitted.

## 11. Phased implementation status and next steps

0. **Phase 0 (closed):** the role/workflow inventory, full-parity release target, conservative tenant-admin/membership defaults, company-level billing-series scope, order-creation numbering, sample-data boundary and external hard gates are recorded in [`PHASE_0_WORKFLOW_INVENTORY.md`](PHASE_0_WORKFLOW_INVENTORY.md).
1. **Phase 1 (complete locally):** the Flask foundation, authentication, account lifecycle, permissions and independent session tests pass locally. Actual two-browser office/MySQL validation is retained for Phase 6 and has not been performed.
2. **Phase 2 (local SQLite verification complete; MySQL gates pending):** schema/importer/backup/tenant-container implementation passes isolated SQLite tests, SQLite Alembic upgrade/schema checks, and offline MySQL DDL generation. None is live MySQL, staging, real restore, or real-media sign-off. The user will run those MySQL checks locally in Phase 6.
3. **Phase 3 (active and unfinished):** a tenant/policy-scoped product catalog is integrated with POS order lines, stable order references allocated at creation, stock deductions on sale/add, stock returns after approved removals, barcode lookup, bounded CSV import/export, and atomic same-company store transfers. Manager/admin settled-order return/refund records now have line limits, idempotency, stock restoration, and cashup netting. Exchanges/credit, tax/discount treatment, return printing, receiving/purchasing integration, category administration, barcode/label printing, and the remaining business modules are open.
4. **Phase 4 (paused; partial slice exists):** durable inventory events, authenticated subscriptions, access rechecks, cursor replay and browser reconnect code are present. Broader module events, multi-worker delivery, offline conflict handling and idempotency remain open; continue only after Phase 3 acceptance.
5. **Phase 5 (not started):** complete role-specific Flask UI and remaining feature/printing parity only after Phase 4 acceptance.
6. **Phase 6 (not started):** after Phase 5 acceptance, perform full MySQL, migration, restore, concurrency, multi-session, two-browser office-network, staging and production-pilot checks before cutover.

The user's latest instruction allows Phase 3 work after isolated SQLite verification while keeping MySQL as the application runtime. Phase 0/1 are complete, Phase 2 local checks pass, and Phase 3 is active but unaccepted. Live MySQL/staging/restore/media validation and the two-browser office test remain explicit Phase 6 gates; no SQLite/offline-DDL result waives them. Phase 4 remains paused until Phase 3 is accepted.

Keep the original Node version unchanged as a comparison/rollback reference until feature parity, data reconciliation and the production cutover are approved.
