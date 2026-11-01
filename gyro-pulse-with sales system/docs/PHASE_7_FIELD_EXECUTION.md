# Phase 7 field execution — prepared tooling, NOT actual field acceptance

The user has confirmed no physical phone, deployed HTTPS pilot or current business operator.
Those resources are still required. No tool here manufactures a pass or waives any gate.
Original apps, prior manifests and historical CI evidence stay unchanged.

## 1. Provision the two distinct hosts

- One dedicated cloud deployment + MySQL database per company, and the existing authoritative
  Retail office. Do not create a second stock ledger or co-locate the office by assumption.
- Select/provision actual hosting, DNS, firewall/SSH administration and secret management first.
  No hosting account, domain, site or production database was available or deployed by this agent.
- Use each isolated copy's own requirements/interpreter and production configuration. Read the
  earlier phase setup before starting. Never use Flask debug/development servers as production.
- Install a reviewed WSGI/Socket.IO-compatible service manager/runtime for the target OS; confirm
  health locally on cloud port5200/office port5100. Restrict these backend ports to their own proxy.
  Do not expose MySQL, Redis, source, backups or private uploads publicly.
- Provision strong independent secrets, dedicated database users and a private rate-limit backend
  as required by deployment concurrency. Put them in the host secret manager, not Git/chat/URLs.
- Set dedicated company/instance/public origin, native production config and secure cookies;
  initialize/bind explicitly using existing commands. Do NOT run empty-database init on live data.
  Review copied `.env.example` files; they are templates, not configured production secrets.
- Configure native trusted cloud origin/connector encryption key, independent P256 recipient key,
  paired office credential and explicit transport permissions. Native LAN ingress remains opt-in.

`deploy/cloud.Caddyfile` and `deploy/office.Caddyfile` are **separate-host proxy templates**.
They restrict TLS1.2/1.3, add HSTS/no-store/nosniff/referrer/frame headers and cap mobile requests.
Set `GYRO_HOST` on the cloud host. On the office host set `OFFICE_HOST`, `OFFICE_TLS_CERT_FILE`
and `OFFICE_TLS_KEY_FILE` to operator-provisioned, protected files. Office DNS must work over LAN
and its certificate must be trusted by Android's SYSTEM CA policy. No trust-all/user-CA bypass.
Cloud automatic certificate issuance requires actual owned DNS/ACME reachability. Do not set HSTS
on a hostname until its HTTPS/key-renewal/recovery policy is reviewed; do not enable preload casually.

Validate with the installed Caddy, then install under the host's reviewed service account/process
supervisor. The templates do NOT configure certificate renewal for office files, access controls,
backend production workers, shared/distributed rate limits, DNS, firewall, backups, migrations,
monitoring or production capacity. Those are site-specific security acceptance tasks, not solved
by placing a Caddyfile in Git. Proxy syntax tests use throwaway fixture certificates, not real TLS.

## 2. Run read-only HTTPS preflight from an authorized machine

From repository root (artifact directory is ignored):
```sh
mkdir -p 'gyro-pulse-with sales system/acceptance-results'
python 'gyro-pulse-with sales system/integration/site_preflight.py' --kind gyro --origin https://YOUR-OWNED-CLOUD-HOST --confirm-owned-site --output 'gyro-pulse-with sales system/acceptance-results/cloud-preflight.json'
python 'gyro-pulse-with sales system/integration/site_preflight.py' --kind retail --origin https://YOUR-OWNED-OFFICE-HOST --confirm-owned-site --output 'gyro-pulse-with sales system/acceptance-results/office-preflight.json'
```
The tool sends at most two uncredentialed GETs, uses platform CA/hostname verification, no proxies,
no redirects/TLS bypass, and checks negotiated TLS, certificate lifetime, health, headers and
anonymous cloud registry denial. No body/customer data, credentials or private cert keys are output.
A pass is **only preflight**. It does not prove rejection of every old TLS version, device trust,
CSRF/role/tenant boundaries, proxy/rate-limit correctness, resilience or a completed security review.
`security_review_accepted` and overall `passed` stay false until independent review; an exit0 means
only preflight checks passed. Without an origin/ownership confirmation, no network call is made.

## 3. Physical Android execution on a dedicated empty phone

Use an authorized test machine with reviewed checkout, ADB, JDK21/Java17 toolchain, SDK35 and
Gradle8.11.1 and SDK `apkanalyzer` on PATH (same build prerequisites as CI). Keep exactly one authorized, booted physical phone
attached. It must be API24+, non-debug OS with green verified boot. Property checks are NOT hardware
attestation or proof of absence of rooting. A security reviewer still verifies key/hardware policy.

**Never run against real pilot data.** Existing release/debug/test pilot packages block this tool;
DO NOT uninstall/clear them to bypass that protection. Gradle may uninstall its newly installed test
packages during cleanup. Use a dedicated clean phone instead. Do not connect another device mid-run.
Use a clean checkout/build-output directory; stale JUnit reports and untracked source block the run.

```sh
# Preflight only. This NEVER counts as executing tests.
python 'gyro-pulse-with sales system/integration/physical_acceptance.py' --output 'gyro-pulse-with sales system/acceptance-results/phone-preflight.json'
# After operator review/confirmation of dedicated empty-phone safety:
python 'gyro-pulse-with sales system/integration/physical_acceptance.py' --run --confirm-disposable-device --output 'gyro-pulse-with sales system/acceptance-results/phone-instrumentation.json'
```
Before installing, the tool builds/decodes both actual APK manifests, verifies the guarded app/test
identities and instrumentation target, and rechecks absence of existing pilot packages. It also
checks reviewed source has not changed during the run. The run requires six exact JUnit cases with zero skips/failures and an APK checksum, rechecks physical
properties, and records source commit/API—not device serial or customer data. It never runs adb
clear/reset/uninstall commands. This covers storage/hash/archive instrumentation ONLY, not app UX,
network/offline/site/key-loss/business acceptance. Nothing is automatically dispatched to hardware.
Local workspace lacks ADB/JDK/Gradle, so current preflight is correctly BLOCKED; no phone was tested.

## 4. Actual outage, site restore and human UAT

Use `PHASE_7_UAT_RECORD.md` with operator/witness and real provenance. Define business load/SLA,
backlog, clock, outage duration and RPO/RTO targets before running. Run order delivery in differing
cloud/LAN/file orderings, perform native receiving/approval, force WAN loss/restart, publish durable
native decisions on recovery, advance catalog, reconcile and verify archive/queue integrity.
Inspect native order/movement/proposal/audit counts—not merely HTTP200 or a green CI job.

Before restore, stop writers/workers/ingress, preserve encrypted queues and immutable IDs, and
restore into an isolated test destination with outbound sync disabled. Restore SQL + native
connector-encryption key + office recipient key/registry/binding/private media using approved secret
custodians. Never restore a cloned office while both old/new offices can write to the same company.
Run native `field-order-audit`; investigate mismatches without clearing queues or generating new IDs.
Use reviewed credential rotation/re-enrollment/replay policy before enabling any outbound sync.
Device-bound `.rga` archives do NOT restore a lost Keystore. Rehearse that failure explicitly and
verify native authoritative records/recovery policy with the operator. Record measured RPO/RTO.
Do not claim production recovery from the disposable CI SQL-only drill.

Only the real business operator/security/backup custodian can sign their witnessed outcomes.
The release inventory remains fail-closed and does not self-authorize production. Phase 8 remains
blocked. Required next resources: hosting/DNS/secret provisioning, dedicated test phone/test machine,
and an available operator—never passwords/tokens/private keys in this conversation.
