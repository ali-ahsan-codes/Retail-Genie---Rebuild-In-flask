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
