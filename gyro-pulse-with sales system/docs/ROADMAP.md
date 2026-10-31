# Phased implementation and application roadmap

Approved design (2026-10-31): use a copy of Retail Genie Final; office Retail Genie owns inventory
and accounting; Gyro Pulse is the field hub; local office receives orders during cloud outages;
complete catalog and orders before payments/delivery/returns. No double stock entry.

## Working rule

Implement one phase, verify it, publish its apply/rollback notes, then obtain approval before
starting the next. A code change, local smoke check and production deployment are different
gates. No phase automatically migrates or replaces a live database. Status is explicit below.

| Phase | Scope | Implementation status |
|---|---|---|
| 1 | Clean copies, isolated config, baseline and roadmap | Implemented; see baseline report |
| 2 | Versioned API contract, company pairing, scoped integrations and API-release UI | Recovery 2A dedicated guard implemented/tested; pairing/UI/credentials still missing |
| 3 | Durable inbox/outbox, identity, acknowledgements and reconciliation foundation | Not started |
| 4 | Catalog/stock snapshots from Retail Genie to cloud/mobile | Not started |
| 5 | Field orders into Retail Genie + authority-side validation/reservation | Not started |
| 6 | Android hybrid routing + authenticated file import/export | Not started |
| 7 | MySQL concurrency, failure recovery, security and catalog/orders release | Not started |
| 8 | Payments/delivery/returns extension with independent acceptance | Deferred |

## Phase 1 — isolated foundation

Deliverables: copied office/server/Android sources; source hash manifest; no copied runtime
secrets/data; database names and development ports isolated; separate dependencies; reproducible
foundation tests; application/rollback instructions. No connection to live systems.

Acceptance: original sources unchanged, copied sources compile as Python, server liveness and
copied backend tests verified, sensitive runtime artifacts excluded. Android build and MySQL
acceptance must be explicitly marked unverified if tooling is unavailable. See BASELINE_REPORT.

Apply: local, separate test installations only, after reviewing PHASE_1_APPLY.md. Nothing syncs yet.
Rollback: stop copied processes; leave originals intact; retain any newly created test database
until inspected. Never run reset/drop scripts against existing databases.

## Phase 2 — API release and pairing

Deliver: `/api/v1` contract, company/branch identities, scoped expiring connector credentials,
issue/rotate/revoke UI, configured canonical cloud/LAN addresses, single-use pairing and audit.
Device identity and integration credentials remain separate; no shared admin/master key.
Connected mode disables independent catalog/stock edits on the field side.

Acceptance: cross-company access denied; revoked/expired credentials rejected; no credentials
in URL/logs; untrusted LAN rejected; pairing replay rejected; only configured addresses exported.
Apply: test company/branch only. Rollback: revoke pairing and disable connector, retain audit records.

## Phase 3 — transport-independent sync foundation

Deliver: durable inbox/outbox in both servers; global event UUIDs; entity mappings; schema version;
per-peer cursors/acks; retry/backoff; quarantine; tombstones; idempotency ledger in the SAME
transaction as business effects. Explicit states: local saved / office received / cloud received /
validated / rejected. No timestamp-only conflict resolution or assumed exactly-once transport.

Acceptance: repeated/out-of-order events, crash-before/after-ack and stale replay produce no
extra business effect; process restarts preserve queue. PostgreSQL/MySQL decisions must be
explicit; target office validation uses supported MySQL/InnoDB, not SQLite locking assumptions.
Apply: test queues only. Rollback: pause worker; preserve queues, never delete pending events.

## Phase 4 — catalog and stock snapshots (one-way authority)

Deliver: Retail Genie publishes products, warehouses, prices, units/taxes and stock availability;
Gyro consumes versioned snapshots/deltas and forwards mobile cache. Display last-confirmed time.
Existing local IDs are mapped, never assumed equal. No stock double entry or shared DB access.

Acceptance: update/delete/reconnect and branch scoping tests; units/decimal prices mapped;
no field endpoint can overwrite authority stock. Snapshot is not a reservation guarantee.
Apply: initial snapshot, inspect counts/mappings, then enable deltas. Rollback: pause consumption;
show stale status and do not reset office stock.

## Phase 5 — orders and office validation

Deliver: field draft/captured order -> hub/local gateway -> office validation -> office reservation
and approval -> status back to field. Offline prices/credit/stock validated by office; shortages
return actionable conflicts, not silent truncation. Cloud receipt is not stock approval.

Acceptance: duplicate file/Wi-Fi/cloud routes create one order/reservation; last-item race tested;
wrong company/customer rejected; rejected order can be reviewed/corrected; legacy hub reservation
paths cannot mutate office-owned stock. Financial posting is outside this phase.
Apply: limited test salesperson/warehouse, compare ledger and order counts before broad enablement.
Rollback: pause intake and preserve received orders; release/reverse reservations via audited workflow,
not destructive deletes.

## Phase 6 — complete hybrid Android + file transport

Deliver: Android durable local store/outbox, trusted cloud/LAN choice, visible sync/rejection UI,
account-scoped queues and Keystore-backed secrets; versioned authenticated encrypted transfer
packages with signed manifests/checksums, batch limits, recipient/company identity and receipts.
Office gateway forwards pending events after internet returns; optional queued order export works
without cloud. Cloud total outage plus office offline means local capture/export only, not sync.

Acceptance: actual Android build/emulator/device; airplane mode, app kill/restart, account switching,
cloud outage, office Wi-Fi, file re-import, tamper/wrong-company rejection; no data loss/double orders.
No assumption that inherited GPC message export already implements the order-transfer contract.
Apply: pilot devices. Rollback: pause transmission but retain device/office outboxes and receipts.

## Phase 7 — catalog/orders release gate

Deliver: security audit (CSRF, throttling, scoped authorization, authenticated encryption, uploads,
key rotation and no shared master secret); MySQL concurrency/load tests; deploy/restore drills;
observability; migrations; Windows/local setup and cloud WSGI/TLS instructions; screenshots.

Acceptance: run the complete morning-online/noon-offline/evening-office/next-day-online scenario,
prove final order and stock reconciliation, backups/restore and API compatibility. Obtain business
UAT approval. No production label until these gates pass. Database rollback must be rehearsed.

## Phase 8 — subsequent finance and logistics

Only after catalog/orders sign-off: payment capture versus accounting-posted states, payment
idempotency, settlement segregation, delivery proof, returns and credit-note/reversal semantics.
Separate design, migration, test and approval gates; never silently overwrite financial entries.

## Multi-office policy

Initial pilot targets ONE authoritative office deployment per company, possibly multiple warehouses.
Multiple independently writable offline office replicas are NOT supported by assumption. Before
extending to that topology, design per-branch authority, allocations and partition conflict rules.

## Checkout recovery notice

The current branch contained only Phase 1, not the later source described in earlier chat.
Recovery 2A is recorded in RECOVERY_2A.md and a separate hash overlay. Later phases remain missing
until code is recovered/rebuilt and tested; no historical chat count is accepted as current evidence.

## Current 2B implementation

Scoped metadata-only office pairing is rebuilt; see PHASE_2B.md for local setup, evidence,
explicit limits and remaining live acceptance. This is not restored transport/catalog/order code.
Phase 3 remains the next implementation step; production and Phase 8 stay gated.

## Phase 3 implementation update

Durable inbox/outbox, retries, lease fencing, duplicate protection, scoped HTTPS endpoints and
an explicit one-shot native worker are implemented. See PHASE_3.md for current test evidence.
Delivery is not business acceptance. Native catalog/order/mobile adapters and real Phase 7
acceptance are not implemented/approved by this update.

## Phase 4 implementation update

Actual native company-owned products, exact prices and store on-hand balances can now be
exported to the durable outbox and explicitly applied as read-only Gyro full-store projections.
See PHASE_4.md for strict pilot limits, source-of-truth semantics, commands and current evidence.
Native human-approved field orders, Android/offline and real acceptance remain next work.

## Phase 5 implementation update

Cloud-admin-vouched immutable order proposals, native business-ID deduplication, human review
and atomic native POS posting are implemented as a bounded operator pilot. See PHASE_5.md.
No mobile agent authorization, cloud decision feedback, actual MySQL concurrency or business
acceptance is claimed. Android/offline and real acceptance remain the next phases.
