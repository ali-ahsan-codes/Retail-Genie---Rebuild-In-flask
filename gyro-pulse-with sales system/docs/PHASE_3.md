# Phase 3 — durable delivery implementation

## Scope and honest status

Implemented in isolated copies only: persistent inbox/outbox, immutable versioned envelopes,
lease recovery/fencing, bounded retries, dead letters, duplicate/conflict handling, cloud HTTP
adapters and an operator-invoked native HTTPS worker. **No stock ledger, catalog application,
order approval/posting, Android app, or production acceptance is supplied by this phase.**

This advances the requested phases, but does **not** complete the user's entire Phase 3–7 list.
The next implementation is Phase 4's real native catalog producer and read-only cloud projection;
Phase 5 must separately validate and human-approve native orders. Phase 6 needs native Android
implementation and device validation. Phase 7 needs real MySQL/TLS/recovery/security and human UAT.

## Transaction and message contract

- Envelopes bind schema, message UUID, company/instance/office UUIDs, direction, kind and payload.
  Canonical UTF-8 JSON is hashed; conflicting reuse of a UUID fails closed, including tenant reuse.
- Only `retail -> gyro: catalog.snapshot` and `gyro -> retail: field.order` directions exist.
  These are transport kinds, **not yet implemented business payload schemas**.
- Maximum envelope 128 KiB; bounded JSON nesting/node count; duplicate keys, nonfinite/floating
  numbers, noncanonical IDs, unexpected schema and cross-company/direction messages are rejected.
  Decimal business quantities/amounts must eventually use explicit canonical decimal strings.
- Enqueue is in the caller's transaction, so a future native source change and its outbox record
  can commit together. Inbox insert/receipt is also caller-transactional.
- Cloud commits inbox **before** returning `status=received`. Native commits inbound inbox
  **before** posting the ACK. A delivery receipt NEVER means applied, approved or stock-posted.
- Lost receipt/ACK causes redelivery, not a second inbox row; an identical envelope produces
  the same receipt. New message IDs for the same business order need Phase 5 business-ID
  idempotency; transport UUID deduplication alone is not enough.
- Leases are durable. Conditional updates and opaque lease tokens fence stale workers; a crash
  permits recovery after expiry. Workers commit leases and release read transactions before I/O.
- Network failures back off exponentially. At eight attempts the message is retained as `dead`,
  not dropped or silently requeued. Invalid receipts are quarantined; receipts are bound to
  envelope hash, recipient and deployment identity. Last-attempt crashes also dead-letter.
- No automatic scheduler, schema setup, unbounded daemon or business writer is started by imports.

SQLite's legacy driver does not automatically BEGIN for SAVEPOINT/SELECT. The shared transport
explicitly establishes its outer SQLite transaction before nested inserts; rollback tests use
normal caller rollback, not a test-only transaction workaround. MySQL uses its normal transaction
and row locks. This is **not evidence of actual MySQL concurrent-worker acceptance**.

## Opt-in permission (no escalation through pairing)

Existing pairing grants and freshly rotated credentials remain `connection:read` only.
After pairing, the cloud administrator uses `/integrations` with CSRF protection to explicitly
**Enable durable transfer** for the current credential. This adds `transport:exchange` to the
credential's existing JSON scope list. Disable removes it immediately; revoke/expiry invalidates
all transport calls. Rotation requires a fresh explicit approval. No existing column is altered.

A pairing bundle cannot request the extra scope. Tests prove scope-tampered grants are rejected.
Legacy role/device keys and wrong company/instance/office headers cannot access transport.

Routes require an active scoped bearer and the three Phase 2B identity headers:

| Route | Meaning |
|---|---|
| `POST /api/v1/sync/messages` | Validate and durably receive an office catalog envelope |
| `GET /api/v1/sync/pull` | Lease at most one cloud field-order envelope for this office |
| `POST /api/v1/sync/ack` | Acknowledge the leased envelope using its exact durable receipt |

The pull response contains a lease token; treat it as private data, not a URL parameter.
Secret-bearing responses are no-store. No inherited stock/order endpoint is unblocked.

## Setup — isolated synthetic pilot only

1. Retain the dedicated Phase 2A binding and complete Phase 2B native pairing/encrypted storage.
   Use separate environments and databases. Do not initialize or migrate original business apps.
2. Back up the isolated pilot. In **each** copied app, using its own Python environment:
   ```sh
   # Gyro, from gyro-pulse/server
   python -m flask --app app init-sync-transport
   # Retail, from retail-genie
   python -m flask --app retail_genie init-sync-transport
   ```
   These explicit commands add only `hybrid_sync_inbox` and `hybrid_sync_outbox`. Factories do
   not create them. Missing cloud transport tables return 503. No destructive migration runs.
3. Explicitly approve current-credential transport through the cloud administrator UI.
4. Native operator can run a bounded cycle:
   ```sh
   python -m flask --app retail_genie field-sync-once --company-id <native-company-uuid> --limit 10
   ```
   It reads that company's pinned connection, decrypts the stored bearer, rechecks the configured
   HTTPS origin allowlist and queries live scoped status before sending. TLS verification is
   mandatory; redirects/environment proxies are disabled. No LAN fallback or browser URL override.
   The terminal receives nonsecret counts or a generic failure. Payloads/tokens are not logged.
5. Until the Phase 4/5 producers exist, only synthetic developer-enqueued transport messages can
   exercise delivery. There is **no automatic product export or native order creation** here.

`connector_enabled=false` / `business_sync_enabled=false` continue to mean no automatic business
connector. Delivery is available only through this explicit permission + operator action.
Use reviewed TLS termination and upstream throttling before any external pilot; do not expose
an HTTP/debug server or assume this phase supplies distributed security/rate-limit acceptance.

## Failure/recovery and rollback

The queues and leases survive process restart. Interrupted pulls reappear after the 300-second
lease; the office returns its already committed receipt. Explicit one-shot sends claim just in
time so later batch jobs do not expire while an earlier network request runs. A failed run may
have committed some deliveries; rerun safely rather than deleting inboxes or regenerating IDs.

Dead letters stay immutable for operator diagnosis. No UI to reset attempts, discard records,
change destinations or replay business writers is introduced. Revoke/disable transport to stop
access, stop the copied process and preserve DB, bindings, encryption keys and receipt evidence.
A tested backup/restore and application/schema rollback drill remains Phase 7 work.

## Evidence

Current suites: **150 passed = 86 Gyro + 52 native Retail + 12 foundation/recovery**.
This includes the existing 2A/2B suites; do not add old historical chat counts to this number.
Coverage includes lost ACK/duplicate delivery, conflicting immutable IDs, normal rollback,
restart/expired leases/stale worker fencing, attempt exhaustion/dead letters, malformed receipts,
cross-identity/direction/scope rejection, native no-network-to-untrusted-origin, admin opt-in,
HTTP push/pull/ACK, large Unicode envelopes, and mocked bidirectional native HTTPS dispatch.

Factory/liveness and dependency checks are run separately in each environment. Original source
hashes remain unchanged; the Phase 3 overlay chains exact previous hashes instead of rewriting
Phase 2A/2B evidence. No runtime DB, tokens, keys or datasets are part of these manifests.

**Not accepted:** real MySQL locking/load, deployed TLS/browser/tenant UAT, native Android,
backup restoration, full offline business scenario, security sign-off or business approval.
This workspace currently has no `mysql`, `docker`, `adb` or `java` executable on PATH. That is a
local tooling observation, not a claim these tests passed elsewhere. Real business UAT cannot
be self-approved by the coding agent. Production and Phase 8 remain blocked.
