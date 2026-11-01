# Phase 6 candidate and Phase 7 acceptance tooling

## Status — not a production-completion claim

Phase 6 implementation now exists, including an isolated Android client candidate. Local evidence:
**230 local tests passed = 122 Gyro + 90 native Retail + 18 foundation/evidence/gate checks**.
The last group includes three fail-closed gate and three report-parser tests, not Android runtime passes.
Separately, real CI built the APK and verified **four executed API35 emulator tests, zero failed/skipped**.
Both factory/liveness and dependency checks remain separate. Original apps remain unchanged.

**Observed bounded CI passes:** actual MySQL8.4 concurrency/transport load, MySQL-backed office
pairing/device enrollment/replay/revoke and signed order dedup, native concurrent approval, actual
logical dump/restore, debug APK compilation and four API35 emulator instrumentation cases.
Evidence: [successful run](https://github.com/ali-ahsan-codes/Retail-Genie-Rebuild-In-flask/actions/runs/41287247244),
`PHASE_7_CI_OBSERVATIONS.json` (tested code commit `6e0613c`). CI artifacts contain the APK/reports;
no binary or private key is committed here. Factory smokes, dependency checks and separate-interpreter
native catalog/order roundtrip also passed. Original app source integrity checks pass.

**Not complete:** physical-device execution, deployed TLS/security and representative business load,
full site/key recovery and outage scenario, native-decision feedback/stale-catalog recovery, retained
order lifecycle and human business UAT. Phase 6 remains a bounded candidate; Phase 7 is NOT fully
accepted. Do not treat emulator storage tests as UI/network/physical-device or business acceptance.

## Implemented security/delivery boundaries

- Dedicated-device credentials are separate from connector, legacy role/device and browser keys.
  Two scopes only: `catalog:read`, `orders:submit`, for the bound company/instance/office/device.
- Active administrator issues a 10-minute, single-use grant bound to active owner, device UUID and
  an out-of-band compared P-256 signing-key fingerprint. Enrollment proves possession of that key.
- Thirty-day device bearer is returned once; server stores its digest only. Rotation requires a
  new grant; owner/signing-key reassignment is blocked. Revoking a device also invalidates pending
  grants. Cloud rejects revoked/expired devices and inactive owners on every request.
- Device orders carry P-256/SHA-256 signatures over exact bounded body bytes containing identities
  and immutable Phase 5 order content. Cloud requires BOTH scoped bearer and valid device signature.
  Devices cannot access office sync endpoints, stock writers or approval/posting methods. Cloud
  mobile routes also fail closed when the authoritative office pairing is revoked/expired.
- Android generates signing and AES-256-GCM state keys in Android Keystore. Credentials, cached
  catalog, immutable signed outbox and receipts are encrypted as one atomic no-backup file.
  Authentication/key loss fails closed; existing data is never silently reset or stored plaintext.
- Connected build has its own application ID (`com.retailgenie.hybrid.pilot`, `.debug` suffix for debug).
  It compiles only `com/example/hybrid`; inherited plaintext preference/GPC/embedded-secret/legacy
  worker code remains preserved on disk but is excluded from the connected APK. No standalone bypass.
  Launcher is `HybridActivity`; backup/transfer, cleartext HTTP and broad file providers are disabled.
- Cloud base URL is operator-approved and compared during enrollment; subsequent requests use the
  enrolled immutable HTTPS origin. Default platform TLS validation, no redirects/proxy discovery,
  no tokens in URLs, logs, saved Activity state or screenshots. No trust-all TLS code.
- Offline order UUIDs are generated once and retained. Identical retries reuse the ID/hash; edits
  require a new proposal (and coordinated rejection of an earlier pending proposal). Local capacity
  is 100 retained orders, 2 MB encrypted state; capacity fails closed instead of deleting unsent data.
- Office parcels use fresh ephemeral P-256 ECDH, RFC5869 HKDF-SHA256 and AES-256-GCM, authenticating
  company/instance/office as associated data. Inner signed proposal is still mandatory. No plaintext
  export or shared-master-secret fallback. File and LAN use the same recipient-encrypted packet.
- LAN uses ONLY an explicitly enrolled office HTTPS origin and encrypted parcel, NEVER the cloud
  bearer/session cookies. LAN/file responses are unconfirmed and cannot clear/ack a device order.
  Only a verified pinned-cloud response with matching business UUID/content hash marks cloud receipt;
  the order is still retained and native approval remains unknown.
- Native LAN/file ingestion validates its private recipient key, scope, signature, device cache and
  expiry, then durably receives/stages a Phase 5 proposal. It does NOT approve/post/deduct stock.
  Deterministic office ingress message IDs plus Phase 5 business-ID mapping reconcile retries across
  cloud, LAN and file paths into one proposal and one eventual human-approved native sale.

## Offline revocation is deliberately bounded, not falsely instantaneous

Office refreshes its device public-key registry directly from the pinned cloud over scoped HTTPS.
No browser/uploaded registry is trusted. An empty/new registry replaces old entries; inactive owner,
revoked and expired devices disappear. The cache's company/instance/office and timestamps are checked.

Default validity is **15 minutes**. Operator may explicitly choose 1–1440 minutes to support a planned
outage. That choice is a security/business policy: an offline office cannot learn a revocation until
refresh, so a longer cache creates that bounded revocation delay. Expired registry fails closed;
there is no infinite offline bypass. Human approval remains mandatory even within the cache window.

## Explicit synthetic-pilot setup

Back up isolated copies first. Use separate environments/databases and existing Phase 2–5 binding,
paired office, explicit connector transport permission, native policies and catalog/order setup.
Factories start no workers, issue no grants and create no schema automatically.

1. Add tables explicitly:
   ```sh
   # Gyro copy, gyro-pulse/server
   python -m flask --app app init-field-devices
   # Native copy, retail-genie
   python -m flask --app retail_genie init-office-mobile
   ```
2. For encrypted file/LAN capability provision an **independent P-256 office recipient key pair** in
   the operator's secret manager. Native `FIELD_OFFICE_PRIVATE_KEY_BASE64` is PKCS8 DER base64;
   cloud `FIELD_OFFICE_PUBLIC_KEY` is corresponding SPKI DER base64. Do not reuse connector/master
   secrets, put private keys in Git/chat/logs, or generate them into this repository. Without this
   configuration Android refuses file/LAN export; it does not fall back to plaintext.
   Set cloud `FIELD_OFFICE_GATEWAY_URL` to the reviewed native office HTTPS origin if LAN is needed.
   Native ingress is off unless `FIELD_LAN_INGRESS_ENABLED=true` is explicitly configured. TLS/edge
   limits must be operator-reviewed before exposing this opt-in signature-authenticated endpoint.
3. Build/install only the connected **debug candidate** in a controlled environment. CI uses JDK21
   for current SDK/Gradle execution and a Java17 Kotlin toolchain/target. Gradle8.11.1, Android SDK35 and SDK/Gradle repositories are needed. Root project now uses a minimal
   AGP8.9.2/Kotlin2.1.20 build instead of legacy Firebase/secrets/KSP dependencies. No wrapper/binary
   is fabricated here; use your installed Gradle/Android Studio or the supplied CI setup.
4. Candidate shows device UUID and signing-key fingerprint. Administrator compares both out of band
   and opens `/integrations/devices`, selects active cloud owner ID and issues a grant. Paste grant
   JSON and operator-approved cloud origin into Android enrollment. Never place secrets in URLs.
5. Download the read-only native store catalog, create a NEW proposal template, fill customer/lines
   and persist the signed encrypted order before network I/O. Device prices/stock are cached
   informational data; native price/stock/permissions are revalidated by human approval.
6. Online: explicitly choose cloud reconcile. Stale catalog/price/business conflicts fail closed and
   retain the order; do not mutate an already queued proposal to force success.
7. Before outage, native operator refreshes the registry:
   ```sh
   python -m flask --app retail_genie field-device-registry-refresh --company-id <company-uuid> --max-age-minutes 15
   ```
   Longer freshness is an explicit reviewed revocation-window choice, not automatic fallback.
8. Offline LAN: choose send to enrolled office HTTPS. Only an encrypted packet goes there. No LAN
   discovery, HTTP downgrade, cloud token or approval is involved. Keep the retained order.
9. Offline file: export `.rgx` via Android Storage Access Framework into a controlled location;
   this contains authenticated ciphertext, not credentials/customer plaintext. Native imports:
   ```sh
   python -m flask --app retail_genie field-device-import --company-id <company-uuid> /controlled/order.rgx
   ```
   Import and LAN use the same transaction/verification path. Repeated exports/imports cannot
   create a second business proposal. Do not use legacy `.gpc` import for this protocol.
10. Native reviewer uses existing Phase 5 UI for explicit approval/rejection. Later cloud sync may
    deliver another transport envelope for the same business ID; it must map to the same decision,
    never another sale. Cloud still has no native decision-return contract; approval stays unknown
    on mobile. Read-only audit after restore:
    ```sh
    python -m flask --app retail_genie field-order-audit --company-id <company-uuid>
    ```
    Missing order/link/audit consistency blocks review/replay; this command never repairs data.

## Candidate limitations needing real acceptance

Manual operator/JSON UI, explicit sync, one enrolled company per installation, bounded catalog/queue,
no user-facing retained-order browser/cancellation wizard, no native decision feedback, no automatic
background retry/scheduling, no large/shared-catalog support and existing restrictive Phase 5 totals.
No biometric/HW-backed-key guarantee is claimed merely because Android Keystore is used. API24 and
API35/device lifecycle, key invalidation, backup/transfer, network/clock and storage-capacity behavior
need runtime tests. The successful API35 run verifies four storage/canonical-hash cases, not the complete app UX or
physical-device/key recovery. Device scopes are company/office-wide across mapped stores, not
per-agent store visibility assignments; native approval still enforces native store permissions.

**Known offline-first reconciliation gap:** if LAN/file is delivered/approved first and the cloud
catalog head advances before the first cloud submit, the strict current-catalog guard may reject
that retained order. Cloud has no native-decision return/repair contract. Never change the existing
order UUID/content or create another sale to force success. This and the 100-retained-order lifecycle
are release blockers, not requirements claimed complete. See `PHASE_7_UAT_RECORD.md`.

## Phase 7 harness and evidence gates

`integration/mysql_acceptance.py` is deliberately destructive **only for exact disposable database
names** and requires `HYBRID_ALLOW_DISPOSABLE_MYSQL=1` plus the matching `HYBRID_MYSQL_TEST_URL`.
It does not accept SQLite/application/live DB names. Separate interpreter cases exercise actual
MySQL REPEATABLE READ: concurrent duplicate inbox inserts/lease claims; concurrent native approvals
must yield one native order/movement/mapping; real mysqldump/mysql restore must preserve stock and
linked decision. No source password or URI is printed. CI uses ephemeral test-only credentials.
The transport duplicate-insert recovery now uses a locking current read to avoid MySQL's older
repeatable-read snapshot hiding the winning insert. SQLite tests alone did not prove this case.

`.github/workflows/hybrid-mysql-acceptance.yml` provisions disposable MySQL8.4, separate interpreters,
real client tools and native restore. Its Android job compiles the candidate and runs four
Keystore/queue/canonical-hash instrumentation cases on API35 emulator, retaining reports/debug APK as CI artifacts.
`integration/android_acceptance.py` requires the exact four JUnit cases with zero skips/failures,
an actual APK checksum and running API35 emulator properties. Target package is asserted during
every test; AGP may correctly uninstall it during cleanup. Failed/queued/unrun jobs are not accepted.
These limited tests do not prove load, all Android devices or complete outage/business scenarios.

`integration/release_gate.py` inventories checksummed evidence for real MySQL, restore, emulator,
physical device, deployed TLS/security, complete offline scenario and human business UAT. It rejects
boolean claims/missing/stale artifacts and **never self-authorizes production**, even if files exist.
File presence and test counts are not approval. Human UAT requires actual business-operator sign-off.

### Current observed external acceptance — 2026-11-01

Successful CI run `41287247244`, code `6e0613ca21676d6a85f2ccb799973f6de94d8375`:

| Check | Observed result |
|---|---|
| MySQL transport load | 200 deliveries, 50 unique messages, 8 workers; 51 inbox rows including initial race case; 0.208s synthetic load observation |
| MySQL concurrency | Duplicate insert/current-read recovery and one simultaneous eligible lease claim |
| MySQL-backed HTTP | Office pairing, device proof enrollment, grant replay rejection, signed-order dedup, device revoke all passed |
| Native concurrent approval | 1 sale, 1 stock deduction/movement and 1 linked audit |
| Actual MySQL dump/restore | Restored stock and proposal-to-native-order mapping matched |
| Android | Debug APK built; 4 API35 emulator tests executed, 0 failed, 0 skipped |
| APK SHA256 | `5fe762d8547c47036e1ce9c5dd56fa2732eaec823eb4c9c59085480c38fa9444` |

Earlier SDK/action, AndroidX and post-test cleanup observation failures were resolved; not every
prior run passed. Exact evidence/provenance is saved in `PHASE_7_CI_OBSERVATIONS.json`. The MySQL
load is a bounded transport test, not an agreed production business SLA. SQL restore does not test
Android Keystore/office-recipient private-key recovery or a site-specific disaster drill.

Physical device, deployed TLS/security/representative business load, full outage/reconciliation
scenario and human UAT remain **pending**. This local workspace has no Java/ADB/MySQL/Docker tools;
actual MySQL and Android observations came from remote CI, not a fabricated local device run.

From repository root, inspect recorded artifacts without authorizing release:
```sh
python 'gyro-pulse-with sales system/integration/release_gate.py' --evidence 'gyro-pulse-with sales system/docs/PHASE_7_EVIDENCE_INDEX.json'
```
This deliberately exits nonzero, with physical-device, deployed TLS/security, full-offline scenario
and human UAT missing. Even all artifacts would require independent provenance/security/business
review; the tool never self-authorizes production. Fill `PHASE_7_UAT_RECORD.md` only with actual
operator results, not invented sign-offs.

Stop/rollback: revoke device/cloud connector access, stop copied workers/ingress and preserve device
ciphertext, keystore, native queues/proposals/sales/audits and office registry/key backups. Do not clear
outboxes, regenerate business IDs, reuse nonces or reset linked decisions. Restore/re-enrollment/key
rotation and revocation-window policy need reviewed drills. Production and Phase 8 remain blocked.
