import importlib.util
from pathlib import Path
import tempfile, unittest, zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "android_acceptance", ROOT / "integration/android_acceptance.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AndroidEvidenceTests(unittest.TestCase):
    def fixture(self, path, skip=False):
        root = ET.Element("testsuite")
        for name in module.EXPECTED:
            case = ET.SubElement(root, "testcase", name=name, classname=module.CLASS)
            if skip:
                ET.SubElement(case, "skipped")
        ET.ElementTree(root).write(path / "TEST-pilot.xml")
        apk = path / "candidate.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr(
                "AndroidManifest.xml", "synthetic unit fixture, not a real APK"
            )
            archive.writestr(
                "classes.dex", "synthetic unit fixture, not runtime evidence"
            )
        return apk

    def test_missing_reports_is_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                module.summarize(Path(tmp), Path(tmp) / "missing.apk")

    def test_skipped_tests_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            apk = self.fixture(path, skip=True)
            with self.assertRaises(ValueError):
                module.summarize(path, apk)

    def test_exact_reports_and_artifact_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            apk = self.fixture(path)
            self.assertEqual(module.summarize(path, apk)["tests_executed"], 4)
            (path / "TEST-extra.xml").write_text(
                '<testsuite><testcase name="unexpected" classname="Legacy" /></testsuite>'
            )
            with self.assertRaises(ValueError):
                module.summarize(path, apk)
