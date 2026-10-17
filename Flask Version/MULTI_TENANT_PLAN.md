# Multi-company and multi-store requirements

**Status: documented, not implemented.** The current Phase 2 MySQL schema and app are still single-company/single-database. This document records the requirements to implement before the Phase 3 business modules; it is not a claim that tenant isolation, store assignments, shared bills, or payment series are already available. Keep `Node Js Version/` unchanged.

## 1. Company and store boundaries

- A **company** is an independent tenant. It may own multiple stores/shops.
- A company's stores share that company's customer and open-order workflow, so an authorized employee at one branch can continue a customer's unpaid bill opened at another branch.
- Different companies must never see or change each other's customers, orders, payments, products, stock, users, reports, uploads, or real-time events. Matching phone numbers in two companies must still resolve only inside the signed-in user's company.
- Store-level data remains scoped to a store unless a workflow below explicitly requires company-wide access. Shared customer bills do **not** automatically mean shared store inventory; inventory visibility and transfers remain store-scoped until separately agreed.

### Isolation architecture recommendation (not yet approved)

The hard requirement is cross-company isolation. The recommended implementation is a small **platform/control database** for the Main Admin and company registry, plus a separate MySQL database and least-privilege database account for each company. All stores belonging to one company use that company's database. Resolve the tenant on the server after authentication; never accept a browser-supplied company ID as authority. Keep database credentials in protected server configuration/secret storage, not in tenant-facing records or browser code.

A shared business database with `company_id` on every row is an alternative, but it has a larger risk of a missed tenant filter. The storage strategy needs explicit sign-off before the schema/import work is changed. The current `DATABASE_URL`/backup implementation assumes one business database, so tenant-aware connection routing, migrations, backups, restore, and retention will be required whichever approach is selected.

## 2. Role hierarchy and shop assignments

The requested hierarchy is:

**Main Admin (Super Admin) → Company Admin (Sub Admin) → Managers → Sales/Cashier staff**

| Role | Required scope and authority |
|---|---|
| **Main Admin / Super Admin** | Controls the platform: creates or disables companies, creates/links company admins, manages company/store setup, and can assign or change a manager's store access in any company. The Main Admin's global control role does not silently grant routine access to every tenant's customer and sales records; any support/data access should be explicitly granted, limited, and audited. |
| **Company Admin / Sub Admin** | Manages only their company: its stores, users, role permissions, settings, and manager-to-store assignments. Can decide which manager is assigned to which store(s), but cannot access another company's tenant data. |
| **Manager** | In normal screens, reports, exports, and inventory workflows, sees only the store(s) assigned by a Company Admin or Main Admin. A manager cannot grant or expand their own assignment. Manager approval for bill-item removals/cancellations is limited to a store the manager is authorized to supervise, unless an audited explicit exception is configured. |
| **Sales/Cashier** | Uses the assigned operating store and only the permissions granted for that role. May use the narrow company-wide open-bill workflow described below; this does not grant access to another store's general reports, inventory, staff, or closed-order history. |

Assignments should be explicit, revocable, and auditable (who assigned whom to which store, when, and by whom it changed). The server must enforce company and store scope in every page, API, search, export, file download, report, and real-time subscription—not just hide navigation links. Permission changes must take effect on subsequent requests and live-event subscriptions.

### Store-scoped manager access and shared bills

Ordinary manager access is limited to the assigned store(s), as requested. Case A also requires a customer to continue an open bill at another store in the same company. The recommended least-privilege exception is a **minimal open-bill view** returned by the phone lookup to an authorized cashier/salesperson at the current company store; it must not expose the originating store's general records. Any change or payment records both the order's original store and the store/user performing the action. A manager may approve a removal for the store where that action is being performed only if assigned/authorized there.

Confirm before implementation whether managers should receive this same limited cross-store bill view, or whether it should be available only to sales/cashier staff and an assigned manager approver. This distinction keeps “manager sees only their shop's data” compatible with company-wide bill continuation.

## 3. Phone lookup and open-bill lifecycle

- A customer phone number alone is sufficient for an authorized employee to search; no OTP or QR code is required for this workflow.
- Normalize the entered number consistently and search **only the authenticated company**. Show that phone's open/unpaid order(s), prioritizing the current company business date. If more than one order matches, show a short list with date/time and originating store so staff select the right bill.
- A partial payment does not close a bill. It remains open and retrievable until the outstanding balance is settled; it must not be auto-closed at midnight. A still-unpaid bill from an earlier date must remain discoverable as open.
- Store the originating store separately from the store handling later item changes or payments. Record each payment with its method, amount, store, cashier, and timestamp. One bill can be continued and paid at any company branch.
- Authorized staff can add items and make permitted edits. Removing an item, cancelling a line, or voiding a bill requires manager approval, a reason, and an append-only audit record containing the actor, approver, affected items/quantities, old and new totals, time, and relevant stores. Do not hard-delete financial history. Recalculate the balance after each approved change.
- Close the bill as paid only when accepted payments cover its final amount. A full cancellation/void is a separate, manager-approved outcome, not a way to bypass payment. If an approved removal makes the paid amount exceed the new amount, record the resulting refund/credit under an explicit policy; never silently discard the difference.
- The date filter should use the company's configured business timezone. Phone lookup is a staff workflow, not customer identity verification; apply the normal staff permissions and log bill mutations/approvals.

## 4. Payment methods and billing/invoice series

- Maintain separate, transaction-safe invoice-number sequences for at least **Cash**, **Bank**, and **Bank Transfer**. An administrator can configure each series (label/prefix and starting/next number) and any additional “Other” series. Changing series settings is audited. Store the payment method(s) separately from the invoice's series classification.
- For a bill paid with multiple methods, the Company Admin configures in advance how that combination is classified for the invoice series—for example, whether a cash-plus-bank-transfer settlement is counted as Cash, Bank, Bank Transfer, or another configured category. Cashiers must not choose an ad-hoc category at checkout. Apply the configured rule consistently and retain the individual tender entries for reconciliation.
- Recommended default: sequences are company-wide across that company's stores to avoid duplicate numbers for cross-store bills. Whether a company instead needs a separate sequence per store must be confirmed before implementation.
- Recommended default: an open order has a stable order reference; the final payment-class invoice series is selected and its number allocated atomically when the bill is fully settled, so a later split-tender payment cannot change an already issued series. Confirm if a numbered tax invoice is legally required before final settlement; if so, define how its series is fixed when the payment mix later changes.
- The existing Phase 2 legacy schema has a single legacy invoice counter. It does not implement these multiple series or mixed-tender rules; the new counters and migration policy must be designed before building checkout.

## 5. Auditing, real-time synchronization, and backups

- Audit bill creation, item additions/edits/removals, approvals/rejections, payments/refunds, closure, store assignment changes, and invoice-series configuration. Keep the log append-only and tenant-scoped.
- Broadcast only committed changes to authorized users in the same company and appropriate store scope. A shared open-bill update may reach authorized staff who can continue that bill; it must never be broadcast to other companies or to managers with no permitted access.
- Backups, restore rehearsals, and retention must cover the platform/control data and every company database. Restore one tenant without exposing or overwriting another tenant. The existing Phase 2 worker currently backs up one configured database and needs a tenant-aware design before production multi-tenancy.

## 6. Acceptance checks before rollout

1. Create two companies with the same customer phone number; a search in either company returns only that company's orders.
2. A cashier at Store B can find an open bill created at Store A in the same company, add an authorized item or record a payment, and the bill and audit show both stores correctly.
3. A partial payment and a date rollover do not close or hide the unpaid bill; full settlement closes it exactly once.
4. A manager assigned to Store A cannot read Store B's general orders, inventory, users, exports, or real-time feed through a URL/API/query. Reassigning them through an authorized admin changes the scope and is audited.
5. Company Admins cannot manage another company. The Main Admin can create companies/admins and manage store assignments, with every privileged change recorded.
6. A removal/cancellation cannot complete without an authorized manager approval; its reason and before/after totals remain auditable.
7. Cash, Bank, Bank Transfer, and configured mixed-tender settlements use the correct independent sequence under concurrent checkout, with no duplicate or reused invoice numbers.
8. Tenant-aware backup/restore testing proves one company's restore cannot expose or alter another company's data.

## 7. Decisions still to confirm before coding

1. Approve the recommended separate-database-per-company approach, or choose a shared database with mandatory tenant keys and constraints.
2. Decide precisely which manager roles may use the limited cross-store open-bill view and which store's manager approves a removal made at another branch.
3. Clarify the earlier phrase “manager daily return/as per collection”: is this an end-of-day cash/bank collection closeout submitted to an admin, a customer merchandise return/exchange, or both? These should be separate workflows if both are required.
4. Confirm whether invoice sequences are company-wide or per store, and whether the final invoice number is assigned at bill opening or full settlement.

Phone-only bill lookup, the role hierarchy, admin-controlled manager/store assignments, unpaid-bill persistence until settlement, separate payment-class series, and an admin-defined mixed-payment classification are captured as requirements from the user. The items above marked “recommended” are implementation defaults, not yet confirmed product decisions.
