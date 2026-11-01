# Retail Genie + Gyro Pulse — isolated hybrid edition

**Recovery state: Phase 1 baseline + reimplemented 2A dedicated-company isolation. Full Phase 2 and later adapters are NOT recovered. Integration and production release remain disabled.**

This directory contains clean, independently configurable copies of the approved source apps.
Original `Retail Genie Final/` and `gyro-pulse/gyro app/` directories are unchanged.
No company databases, passwords, uploads, backups, keystores or screenshot archives were copied.

## Layout

- `retail-genie/`: copy of Retail Genie Final (office stock/accounting authority).
- `gyro-pulse/server/`: copy of the current Gyro Pulse backend (future field hub).
- `gyro-pulse/android/`: copy of the native Kotlin Android project.
- `integration/`: phase gates and foundation verification; **not a running connector**.
- `docs/ROADMAP.md`: scope and acceptance gates for each separately approved phase.
- `docs/DATA_OWNERSHIP.md`: stock/user ownership decisions.
- `docs/PHASE_1_APPLY.md`: safe setup instructions and rollback.
- `docs/BASELINE_REPORT.md`: exactly what was tested and what remains unverified.
- `docs/SOURCE_MANIFEST.json`: source commit, hashes, copied paths and copy-only adaptations.

## Separation defaults

| Application | Development port | Database |
|---|---:|---|
| Retail Genie hybrid copy | 5100 | `retail_genie_hybrid` (MySQL) |
| Gyro Pulse hybrid copy | 5200 | `gyro_pulse_hybrid` (MySQL target); isolated SQLite fallback for development |

Use **separate virtual environments, database credentials and process environments**. Retail
Genie needs Flask 3; the inherited Gyro Pulse requirements currently pin Flask 2. Do not
install both requirements into the same environment or share a DATABASE_URL/SECRET_KEY.

This is a clean source copy, not a second deployment of your existing business data. The copied
Retail Genie schema and Windows installer now target `retail_genie_hybrid`, not the original
database. Other inherited documents describe the upstream standalone app: use this README
and PHASE_1_APPLY.md for this integrated edition. Historical preview images referenced by
inherited guides were intentionally not duplicated; use the originals for reference.

## Phase 1 limits

No API-release UI, pairing, replication, catalog sync, order bridge, file transport or LAN
fallback was added in Phase 1. Existing Gyro Pulse standalone features remain inherited code,
not verified Retail Genie integration. In particular **do not manually maintain the same stock
in both apps**; use synthetic data only until the connected-mode ownership guards are built.

No claim of production readiness or Android build validation. Read BASELINE_REPORT.md.
No production deployment, database initialization or business-data migration is performed
by the baseline checks. Applying each later phase requires separate approval.

See [current recovery evidence and setup](docs/RECOVERY_2A.md). Earlier conversation results do not verify this checkout.

Phase 2B scoped office pairing is now implemented in the isolated copies. See
[setup, protocol and current evidence](docs/PHASE_2B.md). Business sync remains disabled;
Phases 3–7 and real deployment acceptance are not complete.

Phase 3 now adds opt-in durable delivery (not catalog/order application). See
[transport setup, transaction semantics and remaining acceptance](docs/PHASE_3.md).
Phases 4–7 are still incomplete; production remains blocked.

Phase 4 adds bounded, operator-driven actual native catalog exports and read-only Gyro
projections. See [Phase 4 setup and verified limits](docs/PHASE_4.md). The catalog pilot
is limited to 200 company-owned products per store; larger/shared catalogs are rejected,
not silently truncated. Phases 5–7 remain incomplete; no production acceptance is claimed.

Phase 5 adds the [immutable proposal and native human-review pilot](docs/PHASE_5.md).
Cloud submission is administrator-only (not mobile agent auth); native approval uses the
real POS writer and atomically records the business-ID mapping. No payments, automatic
posting or Android support are implied. Phases 6–7 remain incomplete/unaccepted.

Phase 6 now has a scoped-device/encrypted Android **candidate** and authenticated encrypted
LAN/file ingress; Phase 7 gains disposable MySQL/restore/Android CI and a fail-closed evidence
inventory. See [current implementation, setup and explicit acceptance blockers](docs/PHASE_6_7.md).
Source/server test passes do not establish Android/device/TLS/business acceptance.

Observed Phase 6/7 candidate verification: **230 local tests + 4 actual API35 emulator tests**,
real MySQL8.4 bounded concurrency/load and synthetic native dump/restore passed in
[CI run 41287247244](https://github.com/ali-ahsan-codes/Retail-Genie-Rebuild-In-flask/actions/runs/41287247244).
Physical device, deployed TLS/security/business load, full outage/stale-catalog/native-decision
recovery, complete retained-order lifecycle and human UAT remain blocked.
[Operator UAT record](docs/PHASE_7_UAT_RECORD.md) is deliberately unsigned.

Current follow-up: [remaining-code closure candidate](docs/PHASE_6_7_COMPLETION.md) adds trusted native decision feedback, stale-catalog reconciliation and verified encrypted terminal-order archiving. Earlier CI is historical; new CI/device/site/UAT gates still apply.
