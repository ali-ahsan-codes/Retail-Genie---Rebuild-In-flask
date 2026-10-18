# Retail Genie SaaS Tenant-Container Architecture

**Status:** This architecture was documented before implementation as requested, and the user then authorized phased work. The tenant-container schema, active-container context, memberships, company/store assignments, Main Admin-only domain-policy UI with before/after audit history, tenant-aware importer, and scoped sales records are implemented as the current foundation. Local tests pass; live MySQL, realtime isolation, restore, staging, all-module coverage, and production validation remain incomplete. This document does not claim the product is SaaS-production-ready.

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

Enabling inventory sharing does not grant every user permission to edit stock. Giving a role an inventory permission does not let it cross a domain-sharing boundary or a store assignment. The foundation recognizes action-specific membership permissions such as `inventory.view`, `inventory.add`, `inventory.edit`, and `inventory.delete`; existing broad application permissions remain temporarily supported for compatibility. A Main Admin-only policy screen now supports sharing modes and explicit allow/deny unit scopes, increments the policy version, and records before/after values in the tenant audit log. HTTP requests read current policy state; realtime subscription invalidation remains for the later realtime phase.

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
- **Invoice series:** Keep Cash, Bank and Bank Transfer series, and an administrator-configured mixed-tender classification. The scope (container/company/store) and final-number allocation timing are still open; see §10. Do not treat the current draft's company-wide/on-settlement behavior as a final policy.
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
10. Concurrent invoice/payment operations allocate unique numbers once the invoice scope/timing policy is approved.

## 10. Confirmed policy decisions and remaining questions

The user has confirmed the starting domain-sharing policy and authority for this foundation:

- Each domain starts enabled with `company` sharing mode. Broader sharing between child companies requires an explicit setting.
- Only Main Admin may change sharing mode, enable/disable a domain, or edit selected-unit allow/deny scopes. Changes are versioned and audit logged.

Keep these other decisions open rather than hard-coding assumptions:

1. **Invoice series scope:** one sequence per container, per child company, or per branch/store?
2. **Invoice number timing:** at full settlement, first payment, or another point? A mixed tender can make its final classification unknown until later payments; document how reservations/corrections work if numbering occurs earlier.
3. **Child-company role boundary:** may each child company have its own Company Admin who manages only that child/subtree, while the Tenant Admin retains full container scope?
4. **Multi-container staff:** the foundation supports a single login with multiple explicit memberships and requires a container selection at sign-in. Confirm whether this is desired operational policy, or whether customer logins should instead remain separate.

## 11. Phased implementation status and next steps

1. **Documentation first:** complete; the user authorized implementation afterward.
2. **Tenant-container foundation (current phase):** working-tree schema/migration, per-company legacy-container backfill, nested company hierarchy, memberships, active-container selection, role/store scopes, per-domain policy model/enforcement, and tenant-aware legacy/sales records are implemented. Focused and full SQLite test suites pass; MySQL migration SQL generation is supported.
3. **Foundation completion gates:** keep the approved defaults/authority; extend isolation coverage as each module is added; validate with live MySQL, staging, and backup-restore rehearsal before production. Do not treat generated MySQL SQL as a live database test.
4. **Next business modules:** only after the foundation gates are accepted, implement products/catalog and inventory with container/domain/action scoping, then customers, sales and other modules in dependency order.
5. Add permission-scoped realtime delivery and perform full MySQL, restore, concurrency, multi-session, staging and production-pilot checks before cutover.

Keep the original Node version unchanged as a comparison/rollback reference until feature parity, data reconciliation and the production cutover are approved.
