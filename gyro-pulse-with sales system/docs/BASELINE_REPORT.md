# Phase 1 verification report — 2026-10-31

## Result

**Phase 1 foundation implemented and baseline checks passed.**
This is NOT integration acceptance, a deployment, or production-readiness certification.

## Source isolation

- 278 tracked source files copied from Retail Genie Final and the current Gyro Pulse server/Android sources.
- SOURCE_MANIFEST.json records the source commit and original/copy SHA-256 hashes.
- Eight copy-only adaptations: Retail env template, schema DB target, config port, runner port,
  installer DB/user/port; Gyro env template, app DB/port and explicit dotenv path, config JSON.
- Source-hash tests confirm original source files unchanged.
- Excluded runtime databases, environment secrets, uploads, backups, preview archives, caches,
  Android keystores and build artifacts. Backup-engine Python SOURCE files are included.
- Copied Gyro config JSON no longer contains the inherited default admin password block.
- No source database, company records or private files were migrated.

## Checks actually run

| Check | Result | Scope / limitation |
|---|---|---|
| `python -m unittest discover -s integration/tests -v` | 7 passed | Source integrity, exclusion policy, Python syntax, config isolation, disabled integration |
| `baseline_smoke.py retail` in separate Retail venv | Passed | Factory imports, 186 routes registered during manual smoke; /healthz and /readyz return 200 |
| `baseline_smoke.py gyro` in separate Gyro venv | Passed | Factory import; /health returns 200 |
| Copied Gyro `pytest -q .../server/tests` | 14 passed | In-memory SQLite; inherited functional tests; 49 dependency/legacy warnings |
| `pip check` for each separate venv | Passed | No conflicting installed requirements; NOT a vulnerability audit |
| `git diff --check` before staging | Passed for tracked diff only | New copied files were not checked until staging |
| `git diff --cached --check` during PR preparation | Inherited whitespace warnings | Copied upstream files contain trailing whitespace/extra EOF blank lines; preserved to maintain snapshot hashes |
| Manifest sources checked against Git ignore rules | Passed | No copied source files silently excluded from patch |

Runtime tests use ephemeral in-memory SQLite only. No business schema is initialized by the
factory smoke script and no production/company database is accessed. The inherited Gyro
workflow tests create/drop their own in-memory schema. Gyro /health's advertised feature list
is inherited metadata, not proof that all advertised capabilities work.

## Reproduce

Use separate virtual environments. Example from hybrid root:

```sh
python -m unittest discover -s integration/tests -v
/path/to/retail-venv/bin/python integration/baseline_smoke.py retail
/path/to/gyro-venv/bin/python integration/baseline_smoke.py gyro
/path/to/gyro-venv/bin/python -m pytest -q --disable-warnings gyro-pulse/server/tests
```

The Retail smoke script refuses an existing .env.retail-genie because the inherited environment
loader overrides variables from that file. Run checks before configuring a deployment.

## Unverified / remaining

- MySQL client/server, Java and Gradle were not available on PATH; no MySQL schema/installer,
  Windows installation, Android build, emulator, real-device or signed-APK test was performed.
- Retail liveness/readiness only: not POS/accounting or all 186 routes. SQLite SELECT 1 is not a
  MySQL business-schema acceptance check. No new browser screenshots are asserted for Phase 1.
- No cross-application API pairing, catalog/order sync, LAN routing or file bridge exists yet.
- Existing Gyro Android outbox changes remain inherited, unbuilt code; security and device tests
  from its upstream IMPLEMENTATION_STATUS are still outstanding.
- Copied standalone Gyro stock mutation endpoints are not blocked as connected-mode APIs yet.
  Use synthetic data only. Do not run duplicate live stock ledgers pending Phase 2/4.
- Requirements are inherited versions; successful install/pip check is not a CVE/security review.
- Original Retail demo-seeding database-name guard has intentionally NOT been bypassed.
- Original screenshots in inherited documentation are not duplicated. Original guides remain
  reference material; PHASE_1_APPLY supersedes their DB/port instructions for this copy.

## Next approval gate

Review docs/PHASE_1_APPLY.md and the source copies. If accepted, approve **Phase 2: versioned
integration API, scoped credentials, company pairing and connected-mode ownership guards**.
Phase 1 does not automatically apply any phase or start a connector.
