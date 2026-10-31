# Phase 4 — bounded native catalog snapshot implementation

## What is implemented

The active branch extends merged Phases 2B/3, in **isolated copies only**:

1. Native exporter reads actual `Company`, `Store`, `CatalogProduct` and `InventoryBalance` models.
2. It builds an immutable full-store snapshot and queues it through the existing durable outbox.
3. The existing explicitly scoped HTTPS worker sends it to Gyro's durable inbox.
4. An explicit cloud operator application step replaces that store's read-only projection atomically.
5. An authenticated, delivery-scoped read endpoint exposes the latest projection; it does not enable
   legacy stock adjustments, order posting or unrestricted mobile access.

**Retail remains the sole authoritative inventory/accounting ledger.** The exporter does not
create an inventory movement or change balances. The Gyro projection does not write any legacy
`Product`, movement, reservation or stock ledger. On-hand is informational, not available-to-promise.

This is a tested **bounded pilot implementation**, not completion of the entire Phase 4–7 request.
No native field-order approval/posting or Android/offline implementation is added here.

## Precise native mapping and limits

- Explicit native company and active store, with matching tenant/container/company filters.
- Company-owned catalog only. Shared/foreign-owner stock needs a separately designed mapping and
  fails closed; it is never silently combined with company-owned stock.
- Product ID, SKU, barcode, name, category, active flag, price and low-stock price.
- Exact three-decimal price strings from native `Numeric(14,3)` values. Missing price stays null,
  never zero; archived products remain explicitly inactive. Fields are bounded and validated.
- Actual store `quantity_on_hand` and low-stock threshold. No balance means zero. Native negative
  on-hand is preserved as informational data, not corrected by the integration.
- **Currency is null/unspecified.** Native catalog/Company models have no catalog currency field;
  the SaaS subscription currency is not reused as a product-price authority. Do not infer OMR,
  calculate cross-currency totals, or silently post financial amounts from this projection.
- Maximum **200 products per full-store snapshot**, and existing 128-KiB transport/JSON limits.
  More products, oversized fields/envelope or unsupported shared inventory reject the whole export.
  There is no silent truncation, pagination, partial publish or resumable large-catalog protocol yet.
- Empty snapshots are valid full replacements. Deleted products disappear on replacement, and
  absent rows never leave stale old products behind. Product names over 500 characters or invalid
  control characters fail validation rather than being silently rewritten.
- No image fetching, external URL loading, automatic schedules or implicit schema migration.

## Ordering, identity and atomicity

A native per-company/store stream pins the paired instance and office UUIDs and allocates monotonic
sequences under a row lock plus conditional update. Stream increment and outbox insertion share the
caller transaction. Failure rolls back both. No network is called inside the native export transaction.
SQLite pilot reads explicitly establish a real transaction; MySQL relies on repeatable-read semantics,
which must still be verified on a real server before production acceptance.

Gyro applies only a correctly scoped, hash-verified, strictly validated `catalog.snapshot` inbox item.
The latest full payload is a projection row keyed by company/store and pinned instance/office identity.
An application record tracks each processed message separately from its transport receipt:

- Reapplying the same message is idempotent.
- A newer sequence atomically replaces the entire store view.
- An older sequence is recorded as stale and cannot overwrite newer data.
- Reusing a sequence with different immutable envelope bytes is rejected.
- Concurrent update uses row lock/conditional sequence fencing. A concurrent first insert fails a
  unique constraint and requires a full transaction retry; no last-writer-wins fallback is used.
- Invalid messages remain in the durable inbox for diagnosis; the current projection is retained.
- Projection reads return copied data, not mutable ORM JSON objects to callers.

A transport receipt still means **received**, not applied or approved. HTTP transport accepts generic
versioned transport envelopes; payload validation/application is the separate operator step below.
No silent background application or change to existing Phase 3 receipt semantics is introduced.

## Explicit setup and synthetic-pilot workflow

Do not run these commands against original application databases. Preserve isolated backups and
bindings; use separate Python environments/database credentials as documented in Phases 2A–3.
Factories do not create tables or export/apply data.

1. In the native copy (`retail-genie`) initialize only the additive stream table:
   ```sh
   python -m flask --app retail_genie init-field-catalog
   ```
   Existing native company/catalog/store data, pairing and transport tables must already be set up.
2. In the Gyro copy (`gyro-pulse/server`) initialize only the additive projection/application tables:
   ```sh
   python -m flask --app app init-catalog-projection
   ```
3. With an explicitly paired native company, select an actual active store belonging to that company:
   ```sh
   python -m flask --app retail_genie field-catalog-export --company-id <native-company-uuid> --store-id <native-store-id>
   ```
   This queues a message and prints its ID, not its data or credentials. Local operator access is
   trusted server access, not a replacement for browser or mobile tenant permissions.
4. Ensure cloud administrator explicitly enabled the current credential's delivery permission, then:
   ```sh
   python -m flask --app retail_genie field-sync-once --company-id <native-company-uuid> --limit 10
   ```
   Existing pinned HTTPS origin/TLS/redirect protections and queue retry/deduplication remain in force.
5. Apply the delivered message ID on the dedicated cloud:
   ```sh
   python -m flask --app app catalog-apply --message-id <delivered-message-uuid>
   ```
   Requires the matching persistent dedicated binding and pinned office. Rejecting a message does
   not erase its inbox or previous projection. A new corrected export gets a new sequence/message.
6. The office-scoped bearer can read:
   ```text
   GET /api/v1/catalog/snapshot/<native-store-id>
   Authorization: Bearer <active-scoped-secret>
   X-Company-ID: <native-company-uuid>
   X-Instance-ID: <bound-instance-uuid>
   X-Office-ID: <paired-office-uuid>
   ```
   All headers and `transport:exchange` permission are mandatory. Missing tables give 503; missing
   scoped store projection gives 404. This is NOT a device/agent API, and no secret goes in a URL.

Rollback/stop: disable transport, stop copied services and preserve source stream, outbox, inbox,
projection/application history, binding and keys. Never reset sequences or rebind a populated cloud
as an informal rollback. Rehearsed database restore/stream recovery is a Phase 7 gate, not yet passed.

## Current evidence

**171 tests passed: 98 Gyro + 61 native Retail + 12 foundation/recovery.** This includes prior suites,
not an additional 171 tests. There are 76 inherited-style SQLAlchemy legacy-query warnings in Gyro.
Both factory/liveness smoke checks, dependency checks and `git diff --check` pass.

New coverage: actual native product/price/on-hand mapping, no inventory writes, missing/null/inactive
and negative stock semantics, company/store isolation, full transaction rollback, bounded rejection,
read-only authenticated API, idempotent apply, reorder/stale handling, sequence conflict and full
replacement. Contract mirrors and unchanged original source are checked with a chained Phase 4 hash
overlay; older Phase 2A/2B/3 manifests are not rewritten.

An additional offline **two-environment compatibility run** passed:
```sh
python integration/catalog_roundtrip.py --retail-python <retail-venv-python> --gyro-python <gyro-venv-python>
```
It constructs actual native synthetic records, exports through the real native function, pipes the
immutable envelope to a separate Gyro interpreter, persists duplicate-safe receipt/application and
verifies exact price/on-hand projection. Only private in-memory SQLite is used. It verifies no legacy
Gyro stock tables are even created. It is not a deployed HTTPS, MySQL, device or business-UAT test.
The checker and native suite refuse to load a live `.env.retail-genie` file.

## Still pending

- Larger/shared-catalog mapping, pagination/staging and native catalog currency mapping, if required
  for production scope. The bounded pilot above must not be represented as unlimited catalog support.
- **Phase 5:** immutable field-order proposals, native validation/business-ID deduplication, permissioned
  human review and atomic native posting. Existing native `create_order` commits internally: future
  integration must explicitly solve atomic proposal-to-native mapping, not bolt on a second commit
  or write inventory directly. Native current prices/stock/permissions must be revalidated.
- **Phase 6:** encrypted Android persistence, scoped device auth and cloud/LAN/file reconciliation;
  actual Android device testing has not run.
- **Phase 7:** actual MySQL snapshot/worker concurrency, deployed TLS/rate-limit/security review,
  backup/restore and stream recovery drills, the full offline scenario and human business UAT.

`mysql`, `docker`, `adb` and `java` are not present on this workspace's PATH. No real MySQL/Android/UAT
pass is claimed. Business UAT needs real operator sign-off. Automatic business sync and production
release remain disabled; Phase 8 remains gated.
