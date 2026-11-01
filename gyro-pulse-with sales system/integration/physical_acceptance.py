"""Opt-in tests on ONE dedicated empty physical phone. Never clears/uninstalls user data.
Gradle itself may uninstall test APKs: existing pilot packages block execution.
Requires a clean, reviewed checkout, JDK/SDK/Gradle8.11.1 and ADB on the operator's machine.
"""
import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

PACKAGES = ('com.retailgenie.hybrid.pilot', 'com.retailgenie.hybrid.pilot.debug',
            'com.retailgenie.hybrid.pilot.debug.test')
PROJECT = Path(__file__).resolve().parents[1] / 'gyro-pulse/android'


def select_device(output):
    rows = [line.split() for line in output.splitlines()
            if line.strip() and not line.startswith('List of devices')]
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != 'device':
        raise ValueError('Exactly one authorized, online device required; no other devices may be attached')
    if not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', rows[0][0]):
        raise ValueError('Unsupported device identifier format')
    return rows[0][0]


def validate_device(properties, installed):
    if properties.get('ro.kernel.qemu') == '1' or properties.get('ro.boot.qemu') == '1':
        raise ValueError('Emulator is not physical-device evidence')
    api = int(properties.get('ro.build.version.sdk', '0'))
    if api < 24 or properties.get('sys.boot_completed') != '1':
        raise ValueError('Booted API24+ physical phone required')
    if properties.get('ro.debuggable') != '0' or properties.get('ro.secure') != '1':
        raise ValueError('Debug/root-capable OS requires independent security review; do not run')
    # This property check is NOT hardware attestation or proof a device is unrooted.
    if properties.get('ro.boot.verifiedbootstate') != 'green':
        raise ValueError('Verified boot must be green; unknown/unlocked device requires review')
    if any(f'package:{package}' in installed.splitlines() for package in PACKAGES):
        raise ValueError('Existing pilot/test app detected; STOP. Never uninstall or clear it to run this tool')
    return api


def validate_manifests(application_xml, test_xml):
    main=ET.fromstring(application_xml); test=ET.fromstring(test_xml)
    expected='com.retailgenie.hybrid.pilot.debug'
    instrumentation=test.find('instrumentation')
    if (main.get('package')!=expected or test.get('package')!=expected+'.test'
            or instrumentation is None
            or instrumentation.get('{http://schemas.android.com/apk/res/android}targetPackage')!=expected
            or instrumentation.get('{http://schemas.android.com/apk/res/android}name')!='androidx.test.runner.AndroidJUnitRunner'):
        raise ValueError('APK package/target differs from guarded test packages; do not install')


def command(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=30, **kwargs).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Actually run six storage/hash/archive tests')
    parser.add_argument('--confirm-disposable-device', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = dict(schema_version=1, kind='physical_android_acceptance', mode='run' if args.run else 'preflight',
                  preflight_passed=False, passed=False, tests_executed=0, physical_device_accepted=False,
                  production_accepted=False, recorded_at=datetime.now(timezone.utc).isoformat())
    try:
        if args.run and not args.confirm_disposable_device:
            raise ValueError('Explicit dedicated disposable-phone confirmation required; no device commands executed')
        missing = [tool for tool in ('adb', 'java', 'gradle', 'git') if not shutil.which(tool)]
        if missing:
            report['missing_tools'] = missing
            raise ValueError('Required test-machine tools missing; no device commands executed')
        serial = select_device(command(['adb', 'devices']))
        def adb(*params):
            return command(['adb', '-s', serial, 'shell', *params])
        properties = {key: adb('getprop', key) for key in ('ro.kernel.qemu', 'ro.boot.qemu',
            'ro.build.version.sdk', 'sys.boot_completed', 'ro.debuggable', 'ro.secure', 'ro.boot.verifiedbootstate')}
        api = validate_device(properties, adb('pm', 'list', 'packages'))
        command(['git', 'diff', '--quiet'], cwd=PROJECT)
        command(['git', 'diff', '--cached', '--quiet'], cwd=PROJECT)
        if command(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=PROJECT):
            raise ValueError('Clean reviewed checkout required, including untracked source files')
        commit = command(['git', 'rev-parse', 'HEAD'], cwd=PROJECT)
        reports = PROJECT / 'app/build/outputs/androidTest-results'
        if list(reports.rglob('TEST-*.xml')):
            raise ValueError('Old reports detected; use a clean build checkout, never count stale JUnit evidence')
        report.update(preflight_passed=True, android_api=api, source_commit=commit,
                      attestation_verified=False, site_or_business_uat=False)
        if args.run:
            if not args.confirm_disposable_device:
                raise ValueError('Explicit dedicated disposable-phone confirmation required before installing tests')
            env = dict(os.environ, ANDROID_SERIAL=serial)
            if not shutil.which('apkanalyzer'):
                raise ValueError('SDK apkanalyzer required to validate actual APK identities before install')
            subprocess.run(['gradle', ':app:assembleDebug', ':app:assembleDebugAndroidTest', '--no-daemon'],
                           cwd=PROJECT, env=env, check=True, timeout=1200)
            main_apks=list((PROJECT/'app/build/outputs/apk/debug').glob('*.apk'))
            test_apks=list((PROJECT/'app/build/outputs/apk/androidTest/debug').glob('*.apk'))
            if len(main_apks)!=1 or len(test_apks)!=1:
                raise ValueError('Exactly one main/test APK required before any installation')
            validate_manifests(command(['apkanalyzer','manifest','print',str(main_apks[0])]),
                               command(['apkanalyzer','manifest','print',str(test_apks[0])]))
            validate_device({key:adb('getprop',key) for key in properties}, adb('pm','list','packages'))
            # No shell, adb clear, factory reset or explicit uninstall. AGP cleans up ONLY
            # packages whose absence was checked above on this dedicated test phone.
            if select_device(command(['adb', 'devices'])) != serial:
                raise ValueError('Device set changed before run; stop without installing')
            subprocess.run(['gradle', ':app:connectedDebugAndroidTest', '--no-daemon', '--rerun-tasks',
                            '-Pandroid.injected.device.serial=' + serial],
                           cwd=PROJECT, env=env, check=True, timeout=1200)
            # Recheck physical properties after tests; AGP is allowed to remove test apps.
            validate_device({key: adb('getprop', key) for key in properties}, '')
            from android_acceptance import summarize
            apks = list((PROJECT / 'app/build/outputs/apk/debug').glob('*.apk'))
            if len(apks) != 1:
                raise ValueError('Exactly one debug APK required')
            if command(['git','rev-parse','HEAD'],cwd=PROJECT)!=commit or command(['git','status','--porcelain','--untracked-files=normal'],cwd=PROJECT):
                raise ValueError('Reviewed source changed during device run; evidence cannot be attributed')
            report.update(summarize(reports, apks[0]))
            report.update(passed=True, physical_device_accepted=True,
                          acceptance_scope='Six instrumentation cases only; NOT complete UI/network/site/Keystore recovery acceptance')
        else:
            report['next_step'] = 'Preflight is NOT a test pass. Review dedicated-phone safety before --run --confirm-disposable-device.'
    except Exception as error:
        report.update(passed=False, physical_device_accepted=False, failure_type=type(error).__name__)
        if type(error) is ValueError:
            report['blocker'] = str(error)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] or (not args.run and report['preflight_passed']) else 1)


if __name__ == '__main__':
    main()
