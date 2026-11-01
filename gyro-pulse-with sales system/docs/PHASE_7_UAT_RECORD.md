# Phase 7 site/device/business acceptance record — NOT SIGNED OFF

Status: **PENDING**. A developer/agent or automated test cannot fill in human approval.
Use synthetic pilot data first. Never paste keys, tokens, real customer details or database credentials here.
Observed automated CI evidence is recorded separately in PHASE_7_CI_OBSERVATIONS.json.

## Operator-owned provenance

- Company / dedicated deployment / authoritative office: pending
- Reviewed Git commit and installed APK SHA256: pending
- Android device model / OS / security patch / Keystore security level: pending
- Business reviewer, security reviewer and backup custodian: pending
- Test date, timezone and controlled environment: pending
- HTTPS origins / certificate chain / edge configuration evidence reference (no secrets): pending
- Business throughput, p95 latency, concurrency, backlog, RPO/RTO and outage-duration targets: pending
- Approved offline registry freshness and revocation-window policy: pending

## Physical Android and storage

- [ ] Install isolated connected APK, not the original standalone APK. Compare device UUID/fingerprint out of band.
- [ ] Complete valid enrollment; reject wrong owner/key/device/company, expired/reused grant and revoked pairing.
- [ ] Run instrumentation suite on the physical device; retain signed/provenanced reports.
- [ ] Queue while offline, force-stop/reboot/relaunch: exact business UUID/body remains unchanged.
- [ ] Corrupt state/key loss: fail closed, never reset silently, never plaintext fallback.
- [ ] Check backup/device transfer, screenshot/autofill/log exposure and local storage capacity.
- [ ] Check network timeouts/redirects, untrusted/user CA, wrong hostname and clock/lifecycle changes.

## Complete outage scenario (not established by unit tests)

- [ ] Record initial native stock/catalog sequence and native sales/movements baseline.
- [ ] Refresh device registry over trusted cloud channel; record permitted freshness/revocation horizon.
- [ ] Disconnect office WAN, retain reviewed LAN DNS/HTTPS. Field device must remain usable offline.
- [ ] Receive stock locally in Retail Genie; ensure it is the ONLY stock/accounting authority.
- [ ] Create/persist immutable signed device order from cached informational catalog.
- [ ] Deliver encrypted packet by enrolled HTTPS LAN, then the SAME packet via `.rgx` file.
- [ ] Before approval: one pending proposal, zero sales/stock postings. No cloud bearer in LAN/file.
- [ ] Reject a tampered/cross-company/expired/revoked-device parcel; stale registry must fail closed.
- [ ] Native authorized human approves once; unauthorized approver cannot approve. Verify one sale/movement.
- [ ] Restore WAN and retry cloud/file/LAN delivery in different orders, including concurrent retries.
- [ ] Advance the cloud catalog before retrying an offline-first, already-office-approved order.
      Current cloud submission requires a current catalog; it may reject this retained order as stale.
      There is NO implemented native-decision return/repair contract. Do not mutate its UUID/content,
      delete it, or create a replacement sale to force reconciliation. Record and resolve this
      operational gap before claiming complete offline reconciliation/production acceptance.
- [ ] Compare proposal/business UUID, immutable content hash, native order mapping, inventory movement
      and audit counts. Mobile cloud receipt must never be represented as native approval.
- [ ] Demonstrate a reviewed retained-order/recovery procedure; the candidate's 100-order retention
      cap and lack of native-decision feedback are not a full production lifecycle.

## Deployed security, load and real restore

- [ ] Review actual deployed TLS/hostname/CA/origin, trusted proxy, CSRF/session and edge limits.
- [ ] Demonstrate role, store, company, office and revoked/expired device boundary failures on deployment.
- [ ] Run representative MySQL business load and backlog/restart tests against agreed targets;
      the supplied 200-delivery transport test is only a bounded synthetic check, not SLA approval.
- [ ] Restore a controlled site backup on a separate instance; verify stock, native order/proposal
      links/audits, pending inbox/outbox and reviewed credential/key/registry recovery.
- [ ] Recover office recipient key and Android Keystore/identity under the approved threat/recovery
      model. A disposable SQL dump/restore does NOT establish device/private-key recovery.
- [ ] Revoke/rotate credentials after restore and prove replay/idempotency remains safe.
- [ ] Measure actual RPO/RTO; rehearse rollback without clearing queues or undoing audit history.

## Human business decision

- [ ] Actual business operator witnessed/accepted catalog freshness, stock approval, duplicate handling,
      rejection/correction, outage recovery and unresolved-intent handling.
- [ ] Actual security reviewer accepted device/TLS/secret/revocation/recovery policy and residual risks.
- [ ] Native office owner accepted the one-ledger boundary and confirmed no Phase 8 bypass.

Sign-off references and outcome: **PENDING**.
Production / Phase 8 authorization: **NOT GRANTED**.
