# Phase 6–7 remaining-code closure candidate (current branch)

Supersedes earlier remaining-code statements in PHASE_6_7.md, but NOT its historical CI evidence.
Original apps and all earlier integrity manifests/evidence remain unchanged.

## Implemented in this increment

1. **Native decision feedback:** `field-device-decisions-push --company-id UUID --limit 100` reads
   immutable terminal native proposals, verifies content/native sale/scope/review audit, freezes a
   durable decision outbox before any network I/O, and sends to the pinned trusted HTTPS cloud.
   Only an active office connector with `transport:exchange` may POST `/api/v1/devices/decisions`.
   Device tokens, browser sessions and legacy role keys do not authorize publishing decisions.
   Explicit native CLI initialization `init-office-mobile` adds the delivery table; cloud
   `init-field-devices` adds the decision table. No automatic production migration/worker startup.
2. **Stale catalog recovery:** a valid scoped/signed device retry whose UUID/content/owner/device
   exactly matches an already-published terminal office decision receives that native fact even if
   the catalog head advanced. No new proposal/outbox/sale is created by this recovery path.
   New/changed/unknown proposals STILL require the current catalog and all original checks.
   A same-UUID conflicting decision or content is rejected; terminal facts are not overwritten.
3. **Mobile decision refresh:** cloud-received orders are rechecked rather than skipped indefinitely.
   Exact UUID/content-hash receipts are required; approved decisions also require a native order UUID.
   The retained list shows pending/cloud-received/native-approved/native-rejected state. LAN responses
   cannot mark terminal decisions. Receipt denotes the proposal's historical review decision, NOT
   delivery, payment, returns or ongoing financial order state.
4. **Bounded retention lifecycle:** only cloud-confirmed terminal orders can be exported to `.rga`.
   The archive is AES-GCM encrypted with a distinct archive AAD and the device Keystore key; it
   contains signed orders/receipts, NOT bearer/profile credentials. UI writes/closes/reopens the SAF
   document and byte-compares it before atomic queue cleanup. Pending/cloud-only orders cannot be
   pruned. Failed/cancelled/interrupted exports retain orders; cleanup retries are idempotent.
   Read-only "Verify encrypted archive" checks authenticity/scope and displays decision IDs without
   importing pending orders or posting stock. This is DEVICE-BOUND archiving, not portable backup:
   retain the device/Keystore. Losing/uninstalling the app/key can make archives unreadable.

Delivery is explicit: after native approval/rejection and WAN recovery, push decisions, then choose
mobile cloud reconcile, then explicitly archive terminal orders. An outage before ACK leaves a
retryable durable office record; loss after cloud commit repeats the same immutable fact. Native
stock/accounting authority and explicit human approval are unchanged. No Phase 8 functionality.

## Verification status

Current local: 130 cloud + 92 native + 18 integration/evidence tests = **240 local passes**.
New negative/positive cases cover offline-first stale-head recovery, approved/rejected decisions,
unauthorized publishers, scope/device/hash/state conflicts, native audit linkage and outage retry.
Android instrumentation expanded from four to six cases, adding terminal-only encrypted archive,
credential exclusion, pending retention, authenticated tamper rejection and idempotent cleanup.
Fresh CI **passed** for code `e42e9f99f102a9bfb8e47849231ec03e7afd3505`:
[run 41289201599](https://github.com/ali-ahsan-codes/Retail-Genie-Rebuild-In-flask/actions/runs/41289201599).
Both server suites passed in CI; MySQL8.4 additionally verified first-time offline stale-head
reconciliation using a trusted terminal fact, and actual native terminal-record/audit linkage.
Existing real concurrency/load and SQL backup/restore checks also passed.
**Six API35 emulator tests executed, zero failed/skipped**, including actual encrypted archive
credential exclusion, AEAD tamper rejection, pending retention and cleanup idempotency.
APK SHA256: `c918af9bce61ed37bee09fd0d2f9d6e0b28aec01b3c3d510f7ca53be43e2d61f`.
Reports/debug APK are CI artifacts, not Git files. Provenance is in
`PHASE_6_7_COMPLETION_CI.json`. Old four-case evidence remains historical and is not overwritten.

Inspect the current fail-closed inventory from repository root:
```sh
python 'gyro-pulse-with sales system/integration/release_gate.py' --evidence 'gyro-pulse-with sales system/docs/PHASE_6_7_COMPLETION_EVIDENCE.json'
```
It deliberately exits nonzero: real physical-device, deployed security, full site outage/recovery
and human UAT evidence are still missing. This is not blanket Phase 7 or production approval.

## Still requires real acceptance, not fabricated completion

- Actual physical Android phone, lifecycle/IME/storage/backup/Keystore security/recovery tests.
- Deployed HTTPS origins, certificates, proxy/rate limits and security review.
- Representative business workload and agreed SLA/RPO/RTO, full WAN-outage business scenario.
- Site/office-recipient key and Android key-loss/restore policy (device-bound archive is not key backup).
- Actual business operator UAT and sign-off using PHASE_7_UAT_RECORD.md, updated for the new feedback flow.

Physical tests MUST use a dedicated empty test phone. Gradle connected tests may uninstall the debug
package during cleanup: never run them on a phone containing real pilot data, and never clear/reset
app data to recover capacity. A successful emulator run is not physical-device or human acceptance.
Production and Phase 8 remain blocked until real evidence and independent sign-off exist.
