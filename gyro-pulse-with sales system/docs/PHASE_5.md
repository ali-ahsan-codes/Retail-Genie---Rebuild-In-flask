# Phase 5 — immutable field-order / native human-approval pilot

## Delivered, with clear boundaries

Cloud administrators can submit an immutable proposal against the latest applied native store
snapshot. The existing scoped transport sends it to the office inbox. An operator explicitly stages
it for human review. An authorized native approver can reject it without changing stock, or approve
it through the **real Retail POS `create_order` service**. Retail remains the only stock writer.

This is an **operator pilot**, not native Android/agent authorization or production acceptance.
Cloud submission is active-administrator/session/CSRF protected, not a public unauthenticated
agent API. No legacy device/role key is upgraded. Native approval status is authoritative in
Retail and is **not yet synchronized back to the cloud**. Transport ACK remains received only.

No payments, invoices/financial settlement, automatic approvals, delivery/returns, stock reservations,
mobile encryption or LAN/file transfer are introduced. Phases 6–7 and Phase 8 gates remain pending.

## Immutability and duplicate protection

Proposal schema v1 contains exactly:
```
schema_version, order_id, store_id, catalog_message_id,
customer_phone, customer_name, items
```
Each item contains exactly `product_id`, positive integer `quantity`, and positive three-decimal
`unit_price`. No float/bool quantity, arbitrary discount, paid flag, salesperson impersonation,
price override, mutation or extra field is accepted. Limits: 1–50 unique product lines, quantity
1–10,000 each, bounded customer text/phone, supported native total range and existing JSON limits.
The cloud form is bounded by the existing 16-KiB administrative request limit.

- `order_id` is the stable **business UUID**, separate from the transport message UUID. Retrying
  identical data reuses its mapping; changing any immutable field with the same ID is rejected.
- Cloud validates store, active product and exact price against its current scoped catalog head.
  This does not reserve stock or guarantee current office availability.
- Native staging validates hash/contract/company/store and keys proposals by company/business ID.
  Even the same proposal wrapped in a *new transport message UUID* stages only once.
- Identity, snapshot reference, original payload/hash, submitter/reviewer IDs and decision metadata
  are retained. Approval/rejection audits do not duplicate customer phone/name or bearer secrets.
- Final approved/rejected proposals cannot change decision. A corrected proposal needs a new
  business ID, and is NOT an implicit cancellation of an earlier pending proposal. Coordinate
  rejection in Retail first. Do not manually duplicate its sale through POS then approve it again.

## Native authorization, pricing and atomic posting

Review requires an active authenticated actor with `approve_pos`, native company/membership/store
access and sales-view policy. Approval additionally reuses native POS, sales-add, open-bills-add,
product-view and inventory-view/edit permissions. Missing native policies deny access; no tenant
policy or store assignment is seeded/expanded automatically by this feature.

Products are refreshed and locked against the native owning company. The native current unit price
must equal the proposal price; archived/missing/foreign products fail. The native service checks
actual inventory while locking/deducting stock. Cloud cached on-hand never authorizes a sale.

Human review explicitly confirms native POS price units and shows the quoted total. Catalog currency
remains unspecified; no currency is invented/converted. The native final total must equal the quoted
subtotal exactly. Native tax/global-discount rules are NOT overridden to force a match. If they change
the final amount, or prices change, approval rejects/rolls back; use a refreshed/new proposal or a
separately reviewed native POS workflow. No field-side automatic repricing or financial posting.

The copied native POS service adds one optional, typed, **trusted internal** `before_commit` callback.
Existing HTTP payloads cannot supply it, and the default POS path is unchanged. Just before the one
existing native commit, this callback conditionally records pending -> approved, native order ID
and review audit. A failure there rolls back native order, stock movement, balance, order-number
counter and mapping together. No integration stock writer or second post-commit mapping is used.

A repeated approval reads the already approved business mapping and returns the same native order
ID, without a second deduction/bill. Row locking plus conditional pending-state update fence competing
reviews. Real MySQL multi-process concurrency is still a Phase 7 requirement, not a SQLite-test claim.
If commit acknowledgement is lost, reload the native business-ID decision before retrying; never
create a new business ID just to bypass an uncertain response.

## Setup and explicit pilot workflow

Use the isolated copies, separate Python environments and databases. Back up pilots first. Complete
Phases 2A–4 binding, paired encrypted credential, explicitly enabled transport and applied catalog.
Factories do not initialize proposal tables or post sales automatically.

1. Add the proposal tables explicitly:
   ```sh
   # Gyro, from gyro-pulse/server
   python -m flask --app app init-field-orders
   # Retail, from retail-genie
   python -m flask --app retail_genie init-field-orders
   ```
   These are additive tables; no production/live migration or existing business-data adoption runs.
2. Active cloud administrator opens `/integrations/orders` (also linked from `/integrations`).
   Current scoped store/snapshot IDs are listed. Submit strict JSON, for example:
   ```json
   {
     "schema_version": 1,
     "order_id": "<new-stable-business-uuid>",
     "store_id": "<native-store-id>",
     "catalog_message_id": "<current-applied-catalog-message-uuid>",
     "customer_phone": "+96800000000",
     "customer_name": "Synthetic pilot customer",
     "items": [
       {"product_id": "<native-product-id>", "quantity": 2, "unit_price": "1.250"}
     ]
   }
   ```
   Placeholder strings must be replaced with real synthetic-pilot IDs; the example is not executable
   as-is. Copy exact current native price strings. Retry identical data with the same business UUID.
3. Native operator runs the existing `field-sync-once` for that company. The cloud order is leased,
   durably received in the office inbox and ACKed. No native sale or stock deduction occurs here.
4. Stage the delivered transport message ID, not the business ID:
   ```sh
   python -m flask --app retail_genie field-order-stage --company-id <native-company-uuid> --message-id <transport-message-uuid>
   ```
   Current pilot operators obtain that ID from trusted queue/inbox administration. Automatic inbox
   staging, notifications and an inbox-selection UI are not supplied by this bounded implementation.
5. Native approver opens `/settings/field-orders`. Native super-admin may select an authorized
   company with `?company_id=<native-company-uuid>`; ordinary accounts use their native membership.
   The page shows up to 200 recent staged proposals visible under native store/sales permissions.
6. Review customer, product IDs, quantities, price units and total. Explicitly tick native price
   confirmation before approving, or reject with a bounded reason. Flask-WTF CSRF is required.
   Successful approval creates a native **open bill**, with one native stock movement. No payment
   is recorded, and approval does not close/invoice the bill automatically.
7. Check final status/native order ID in Retail. Cloud UI cannot claim that this proposal was
   approved/rejected: decision feedback requires a future versioned return-message contract.

Stop/rollback: disable connector transport, stop copied workers and preserve proposal/mapping/audit
and native POS data. Never delete a business-ID mapping or reset an approved proposal to pending.
Do not restore queues independently from native sales mappings without a rehearsed consistency drill.
Atomic linked restore/concurrency/security/UAT acceptance remains Phase 7 work.

## Verified evidence

**197 tests passed = 106 Gyro + 79 native Retail + 12 integrity/recovery.** This includes prior
phases; it is not an extra 197 tests. Gyro reports 85 existing-style legacy-query warnings.

New checks cover cloud immutable-ID dedup/conflict, exact catalog references/prices, strict numbers,
CSRF/admin UI, native new-message/same-business dedup, no stock changes on receipt/staging/rejection,
actual native POS approval exactly once, final decisions, inactive/nonapprover and real sibling-company
membership denial, actual company-admin posting, missing policy denial, tampered stored payload,
native review confirmation/CSRF, unchanged default POS path and full rollback after price/archive/
stock/tax/audit-callback failures (including native series and stock movement).

An additional offline compatibility check passed using separate interpreters:
```sh
python integration/order_roundtrip.py --retail-python <retail-venv-python> --gyro-python <gyro-venv-python>
```
It uses actual native catalog export, actual cloud catalog application/proposal generation, durable
native receipt/staging, and actual native POS review. Duplicate approval creates one bill, one stock
deduction and zero payments. SQLite databases are private/in-memory; no network/TLS acceptance is
claimed. This builds on the separate catalog roundtrip check. Neither checker loads a live native
environment file or writes synthetic datasets/credentials to the repository.

Both factory/liveness and dependency checks pass separately. Original applications and older evidence
manifests remain unchanged; the new Phase 5 overlay chains exact previous hashes, including the small
copied native POS callback change. Nothing is marked production ready by test counts.

## Remaining work

**Phase 6:** device enrollment/scoped auth, Android encrypted storage, offline immutable business IDs,
cloud/LAN/file reconciliation and actual device testing. Admin-proposal UI is not a substitute.

**Phase 7:** actual MySQL locking/concurrent approval/idempotency, deployed TLS/security/rate limiting,
backup/restore of queues plus linked native sales, full offline reconciliation scenario and human
business UAT. No Android/MySQL tools or human UAT evidence are available here; no pass is fabricated.

Pilot limitations above (manual staging, no cloud decision feedback, restrictive total policy and
bounded catalog/proposal sizes) need explicit product/business acceptance before a wider release.
Automatic business sync and production release remain gated. Finance/logistics Phase 8 is not enabled.
