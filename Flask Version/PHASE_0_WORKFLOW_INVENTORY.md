# Phase 0 — Legacy workflow and first-release scope inventory

**Status:** Phase 0 scope baseline completed at the user's direction. It is based on the checked-in `Node Js Version/src/app/` pages, `src/components/layout/AppSidebarContent.tsx`, role/permission constants, API route tree, and the user's confirmed requirements. To close the remaining decisions without weakening tenant security or dropping features, the baseline choices below use least privilege and preserve legacy behavior. They are explicit and may be revised by the user before the affected phase is accepted. The legacy application remains an unchanged reference.

## 1. Legacy roles and visible workflows

| Legacy role | Workflows visible in the reference app | Review notes |
| --- | --- | --- |
| **Admin** | Admin dashboard; products/stores and inventory; orders/POS; quotations; demand notices; returns; suppliers and SCM/purchase orders; accounts/users; audits; reports/activity and salesperson reports; breaks/attendance; settings (tax, discount, commission, invoice numbering); cloud/file administration; label printing; messaging; profile. | In the legacy app this role has broad administration. In the Flask tenancy model, distinguish platform Main Admin/Super Admin from a tenant/company Admin. Baseline: a child-company Admin manages only that company and its assigned stores; broader scope requires explicit Main Admin delegation. |
| **Manager** | Permission-selected admin/operational dashboards and the management, order, product, quotation, demand-notice, user, SCM, audit, report, settings and file workflows granted to that manager. Also sales, cashier, store and logistics operational dashboards. | Keep manager permissions and assigned store scope independently enforced. The user has confirmed manager cross-store bill access is controlled by an administrator; removals/cancellations require manager approval and audit. |
| **Salesperson** | Sales dashboard and sales/POS work; store selection/external stores; demand notices; quotations; sales reports; customer/order follow-up; profile, attendance/breaks, personal cloud files and messaging. | Bill lookup by phone is sufficient. Authorized staff in a container can continue an open bill at another store; an unpaid bill remains open until payment clears. |
| **Cashier** | Cashier dashboard; checkout/payment and open-bill workflows; shift summary; profile, attendance/breaks, personal cloud files and messaging. | Preserve distinct Cash, Bank and Bank Transfer billing series. Mixed-tender classification is configured by an admin. |
| **Express** | Express checkout; profile and shift summary; personal cloud files and messaging. | Keep it as a distinct, restricted checkout workflow in the full-parity release target. |
| **Storekeeper** | Store dashboard; stock receiving; demand notices; relevant purchase-order/stock workflows; profile, attendance/breaks, personal cloud files and messaging. | Inventory write access must remain permission- and store-scoped; receiving and stock changes need transaction/audit behavior. |
| **Logistics** | Logistics dashboard; purchase-order tracking and logistics details/status; authorized purchase-order attachments; relevant reports; profile, personal cloud files and messaging. | The legacy admin layout permits logistics users on selected PO detail routes only. Preserve route-level restrictions, not only hidden navigation. |
| **Auditor** | Assigned audits; audit execution/counting, evidence/images and reports; profile, attendance/breaks, personal cloud files and messaging. | Audit access must be distinct from inventory editing; keep evidence and audit history scoped and protected. |
| **Display** | LCD order display. | The display is a read-only operational surface and must not expose another container's orders. Keep it as a read-only surface in the full-parity release target. |

## 2. Cross-role business areas found in the reference

1. **Identity and operations:** login/profile/password; role/permission-controlled navigation; user lifecycle; attendance and breaks; activity logs.
2. **Sales and money:** product lookup/barcode use; cart and checkout; customers and phone lookup; open/unpaid/partially paid orders; continuation across authorized stores in the same container; tender/payment records; billing series; removals/cancellations and approval; returns/exchanges/refunds; cash/bank closeout.
3. **Product and stock:** catalog/category/SKU/barcode, pricing and low-stock metadata; stock balances and receiving; supplier products; purchase orders and attachments; demand notices and conversion; audits/counts.
4. **Commercial workflows:** quotations and conversion to demand notices/orders; salesperson assignment/reporting; discounts, tax and commission settings.
5. **Collaboration and support:** internal messaging/conversations/attachments; personal cloud files and admin file management; activity/audit history; reports and exports.
6. **Special surfaces:** barcode/label printing, thermal invoice/receipt printing, and LCD order display.
7. **Platform/tenant operations:** company and branch/store setup; memberships and store assignment; domain-sharing policy; automatic backups and legacy import/reconciliation.

The current Flask working tree implements only a subset of these workflows. Its existing code is not evidence of Phase 0 sign-off or full feature parity.

## 3. Phase 0 decisions and acceptance baseline

- Keep the app Python/Flask/MySQL with no Node.js runtime or npm build dependency; keep the legacy Node app unchanged as a reference.
- Use one shared database with a separate logical `tenant_container_id` per independent customer; companies/branches are nested within it; never share business data across containers.
- Start with conservative company-level sharing. Only global Main Admin controls domain-sharing policy. Domain policy, role/action permissions and manager-controlled store assignment all apply together.
- A standalone company gets its own container; child companies/branches may join a selected container. **Tenant-admin scope:** a child-company Admin manages only that company and its stores by default; any broader authority requires an explicit Main Admin delegation.
- **Staff memberships:** a normal staff login is restricted to one container by default. If cross-container staffing is operationally required, only explicit Main Admin-granted memberships are allowed, with an active-container selection per session and no cross-container queries or sharing. A Main Admin is the separate platform-level exception.
- Within an authorized container, support cross-store open-bill continuation according to configured permissions; phone-only lookup is sufficient; unpaid bills remain open until payment clears; removals/cancellations require manager approval and audit.
- **Billing numbers:** maintain separate Cash, Bank and Bank Transfer invoice series per legal company, shared across that company's stores. Allocate a stable order reference when an order is created, matching the legacy POST-order flow; allocate the tender-specific invoice number when the bill is fully settled. An unpaid order remains open and unpaid until settlement. Admin configures mixed-tender classification.
- Daily manager “return/as per collection” means end-of-day cash/bank closeout. The admin configures automatic backup interval; dumps go under the app's `backup/` directory.
- **Release scope:** all workflows in the role inventory remain must-have parity targets for the first usable release. Work may be prioritized by dependency across Phases 1–6, but no legacy module/role is excluded or deferred from the release target without explicit user approval.
- The checked-in `Node Js Version/netpos.db` is sample data, not production data. No production database or `uploads/` directory is present in this checkout; an external production source, if any, remains unidentified and must never be inferred from the sample.
- The confirmed deployment shape is a shared office/local-network server. The exact host OS, LAN/TLS configuration and persistent backup path are not available in this checkout and are recorded as deployment gates before production pilot/cutover.

## 4. First-usable-release acceptance target

The first usable release targets **full parity for every role and workflow in Sections 1–2**, including platform and tenant administration, account/permission/store scope, POS and open bills, products/inventory, all payment/tender rules, approvals/removals, returns/exchanges, closeout, reports, SCM/receiving, demand notices/quotations, attendance/breaks, audits/evidence, messaging/files, printing, and the LCD display. Phase ordering may prioritize dependencies, but nothing is removed from the target without the user's explicit approval. A production launch additionally requires Phase 6's live MySQL, migration reconciliation, restore, hosting/security, pilot and cutover evidence.

## 5. Phase 0 closure record

Phase 0 is closed as a **scope and safe-development baseline**: the role/workflow inventory is recorded, all legacy workflows remain in scope, conservative tenant-admin and membership defaults are explicit, billing-series scope/timing preserve company/legal-entity separation and the reference app's order-creation numbering, and the local database/media boundary is documented. This does not claim production data was found, backed up, migrated or validated.

**Hard gates carried into later phases:** identify any external production database/media and make a verified restorable backup before Phase 2 import/conversion; validate live MySQL and import reconciliation in staging during Phase 2; confirm host OS/LAN/TLS and persistent/off-host backup arrangements before Phase 6 pilot/cutover. Until then, never import the checked-in sample as production or deploy the app to a shared office network.
