"""Observe actual emulator/JUnit/APK evidence; missing/skipped/no-source is never a pass."""

import argparse, hashlib, json, os, subprocess, zipfile
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

EXPECTED = {
    "archiveOnlyTerminalAfterVerifiedExportKeepsPending",
    "corruptArchiveCannotRemoveOrders",
    "encryptedIdentitySurvivesRecreation",
    "modifiedCiphertextFailsClosed",
    "immutableQueueEncryptedAcrossRestart",
    "canonicalHashMatchesPythonUnicodeVector",
}
CLASS = "com.example.hybrid.HybridKeystoreTest"


def summarize(report_dir, apk):
    files = sorted(Path(report_dir).rglob("TEST-*.xml"))
    cases = []
    if not files:
        raise ValueError("No actual JUnit reports")
    for path in files:
        cases.extend(ET.parse(path).getroot().iter("testcase"))
    if len(cases) != len(EXPECTED) or {case.get("name") for case in cases} != EXPECTED:
        raise ValueError("Exact connected-mode test coverage missing")
    if any(
        case.get("classname") != CLASS
        or any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
        for case in cases
    ):
        raise ValueError("Failed/skipped/wrong-class tests")
    apk = Path(apk)
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        if "AndroidManifest.xml" not in names or "classes.dex" not in names:
            raise ValueError("Not an installable candidate APK archive")
    return dict(
        tests_executed=len(cases),
        tests_failed=0,
        tests_skipped=0,
        test_names=sorted(EXPECTED),
        apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        project = Path(args.project).resolve()
        apks = list((project / "app/build/outputs/apk/debug").glob("*.apk"))
        if len(apks) != 1:
            raise ValueError("Exactly one actual debug APK required")
        checks = summarize(project / "app/build/outputs/androidTest-results", apks[0])

        def adb(*command):
            return subprocess.run(
                ["adb", "shell", *command],
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
            ).stdout.strip()

        if (
            adb("getprop", "ro.build.version.sdk") != "35"
            or adb("getprop", "ro.kernel.qemu") != "1"
        ):
            raise ValueError("Actual API35 emulator required")
        # AGP is allowed to uninstall apps during task cleanup. Target package is
        # asserted INSIDE every instrumentation case, not inferred after cleanup.
        checks["package_present_after_test_cleanup"] = (
            "package:com.retailgenie.hybrid.pilot.debug"
            in adb(
                "pm", "list", "packages", "com.retailgenie.hybrid.pilot.debug"
            ).splitlines()
        )
        checks.update(
            android_api=35,
            emulator=True,
            physical_device=False,
            target_package_verified_by_instrumentation="com.retailgenie.hybrid.pilot.debug",
        )
        passed = True
    except Exception as error:
        # This helper handles only synthetic JUnit/APK/ADB metadata, no credentials.
        checks = {
            "failure_type": type(error).__name__,
            "failure_message": str(error)[:500],
        }
        passed = False
    report = dict(
        schema_version=1,
        side="android",
        passed=passed,
        checks=checks,
        commit=os.environ.get("GITHUB_SHA"),
        run_url=os.environ.get("ACCEPTANCE_RUN_URL"),
        recorded_at=datetime.utcnow().isoformat() + "Z",
        production_accepted=False,
    )
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    print(
        "::"
        + ("notice" if passed else "error")
        + " title=Hybrid observed android::"
        + json.dumps(report)
    )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
