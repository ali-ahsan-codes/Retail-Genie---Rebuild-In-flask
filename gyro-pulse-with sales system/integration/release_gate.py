"""Fail-closed acceptance inventory, NOT automatic production authorization.
Even complete local/CI evidence needs independently reviewed physical-device and human UAT sign-off.
"""

import argparse, json, shutil, hashlib
from pathlib import Path

REQUIRED = (
    "real_mysql_concurrency",
    "backup_restore",
    "android_emulator",
    "android_physical_device",
    "deployed_tls_security",
    "full_offline_scenario",
    "human_business_uat",
)


def gate(evidence=None):
    evidence = evidence or {}
    checks = {}
    for name in REQUIRED:
        entry = evidence.get(name)
        valid = False
        if (
            isinstance(entry, dict)
            and entry.get("passed") is True
            and isinstance(entry.get("artifact"), str)
            and isinstance(entry.get("sha256"), str)
        ):
            artifact = Path(entry["artifact"])
            if artifact.is_file():
                valid = (
                    hashlib.sha256(artifact.read_bytes()).hexdigest() == entry["sha256"]
                )
        checks[name] = valid
    return dict(
        schema_version=1,
        checks=checks,
        missing_evidence=[name for name, passed in checks.items() if not passed],
        tools={
            tool: bool(shutil.which(tool))
            for tool in ["java", "adb", "mysql", "mysqldump", "docker"]
        },
        all_artifacts_present=all(checks.values()),
        release_permitted=False,
        reason="Artifacts require independent provenance/security/business review; this inventory never self-authorizes production.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence")
    args = parser.parse_args()
    evidence = json.loads(Path(args.evidence).read_text()) if args.evidence else {}
    result = gate(evidence)
    print(json.dumps(result, indent=2))
    raise SystemExit(1)
