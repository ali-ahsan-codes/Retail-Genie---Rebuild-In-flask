"""Synthetic fixtures only: never phone/site acceptance evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'integration' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


physical = load('physical_acceptance')
site = load('site_preflight')


class PhoneSafetyTests(unittest.TestCase):
    def props(self):
        return {'ro.kernel.qemu': '', 'ro.boot.qemu': '', 'ro.build.version.sdk': '35',
                'sys.boot_completed': '1', 'ro.debuggable': '0', 'ro.secure': '1',
                'ro.boot.verifiedbootstate': 'green'}

    def test_single_authorized_device(self):
        self.assertEqual(physical.select_device('List of devices attached\nfixture-serial\tdevice\n'), 'fixture-serial')

    def test_no_or_multiple_or_unauthorized_devices(self):
        for value in ('List of devices attached\n', 'a\tdevice\nb\tdevice', 'a\tunauthorized', 'a\toffline', 'a&bad\tdevice'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                physical.select_device(value)

    def test_emulators_and_unknown_or_unlocked_boot_blocked(self):
        for key, value in [('ro.kernel.qemu', '1'), ('ro.boot.qemu', '1'), ('ro.boot.verifiedbootstate', ''),
                           ('ro.boot.verifiedbootstate', 'orange'), ('ro.debuggable', '1'),
                           ('ro.secure', '0'), ('sys.boot_completed', '0'), ('ro.build.version.sdk', '23')]:
            properties = self.props(); properties[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                physical.validate_device(properties, '')

    def test_existing_pilot_or_test_package_blocks_without_deleting(self):
        for package in physical.PACKAGES:
            with self.subTest(package=package), self.assertRaises(ValueError):
                physical.validate_device(self.props(), 'package:' + package)

    def test_actual_apk_package_and_instrumentation_target_must_match_guards(self):
        package='com.retailgenie.hybrid.pilot.debug'
        main='<manifest package="'+package+'" />'
        test='<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="'+package+'.test"><instrumentation android:targetPackage="'+package+'" android:name="androidx.test.runner.AndroidJUnitRunner" /></manifest>'
        physical.validate_manifests(main,test)
        for first,second in [(main.replace(package,'other.real.app'),test),
                             (main,test.replace('targetPackage="'+package+'"','targetPackage="other.real.app"')),
                             (main,test.replace('AndroidJUnitRunner','WrongRunner'))]:
            with self.assertRaises(ValueError):physical.validate_manifests(first,second)

    def test_run_without_consent_stops_before_any_device_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'phone.json'
            result=subprocess.run([sys.executable,str(ROOT/'integration/physical_acceptance.py'),
                '--run','--output',str(output)],capture_output=True,check=False)
            self.assertEqual(result.returncode,1)
            report=json.loads(output.read_text())
            self.assertFalse(report['passed']);self.assertEqual(report['tests_executed'],0)
            self.assertIn('no device commands',report['blocker'])

    def test_empty_compatible_phone_preflight_only(self):
        self.assertEqual(physical.validate_device(self.props(), 'package:android'), 35)


class SiteSafetyTests(unittest.TestCase):
    def transport(self, status=200, body=None, headers=None, auth=401, version='TLSv1.3', days=30):
        self.paths = []
        def send(host, port, path):
            self.paths.append(path)
            if path == '/api/v1/devices/registry':
                return auth, {}, b'{}', {}
            return status, headers if headers is not None else {'content-type': 'application/json',
                'strict-transport-security': 'max-age=31536000', 'x-content-type-options': 'nosniff'}, body if body is not None else json.dumps({'status':'healthy','deployment_mode':'dedicated'}).encode(), {'tls_version':version, 'certificate_days_remaining':days}
        return send

    def test_strict_origins(self):
        self.assertEqual(site.checked_origin('https://office.example.test:8443/'), ('office.example.test',8443))
        self.assertEqual(site.checked_origin('https://[::1]'), ('::1',443))
        for origin in ('http://host', 'https://user:secret@host', 'https://host/path',
                       'https://host?token=x', 'https://host#x', 'https://host?', 'https://host#',
                       'https://host:0', 'https://host:65536', 'https://host/\n',
                       'https://*.example.test', 'https://host\\evil', 'https://bad_host', 'https://é.test'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                site.checked_origin(origin)

    def test_bounded_read_only_gyro_preflight(self):
        report = site.probe('https://fixture.example.test','gyro', self.transport())
        self.assertTrue(report['preflight_passed'])
        self.assertEqual(self.paths, ['/health','/api/v1/devices/registry'])
        self.assertFalse(report['credentials_sent']); self.assertFalse(report['business_writes'])

    def test_redirect_bad_json_and_unready_or_anonymous_access_fail(self):
        for values in ({'status':302}, {'body':b'not json'}, {'auth':200}, {'auth':503},
                       {'version':'TLSv1'}, {'days':13}, {'headers':{}},
                       {'body':b'{"status":"healthy","deployment_mode":"standalone"}'}):
            with self.subTest(values=values):
                self.assertFalse(site.probe('https://fixture.example.test','gyro',self.transport(**values))['preflight_passed'])

    def test_retail_health_only(self):
        report = site.probe('https://fixture.example.test','retail',self.transport(body=b'{"status":"ok"}'))
        self.assertTrue(report['preflight_passed']);self.assertEqual(self.paths,['/healthz'])

    def test_invalid_port_never_reflects_secret_like_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'report.json'
            marker='accidental-private-port-marker'
            result=subprocess.run([sys.executable,str(ROOT/'integration/site_preflight.py'),
                '--kind','gyro','--origin','https://host:'+marker,'--confirm-owned-site',
                '--output',str(output)],capture_output=True,check=False)
            self.assertEqual(result.returncode,1)
            self.assertNotIn(marker,output.read_text())
            self.assertNotIn(marker,result.stdout.decode())

    def test_no_origin_or_consent_makes_no_network_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'report.json'
            result = subprocess.run([sys.executable,str(ROOT/'integration/site_preflight.py'),
                '--kind','gyro','--output',str(output)],capture_output=True,check=False)
            self.assertEqual(result.returncode,1)
            report=json.loads(output.read_text())
            self.assertFalse(report['passed']);self.assertFalse(report['security_review_accepted'])
            self.assertIn('no network calls',report['blocker'])
