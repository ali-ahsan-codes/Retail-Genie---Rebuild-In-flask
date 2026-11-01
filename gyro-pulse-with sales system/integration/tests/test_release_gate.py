import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "release_gate", ROOT / "integration/release_gate.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseGateTests(unittest.TestCase):
    def test_no_evidence_blocks_every_gate(self):
        report = module.gate()
        self.assertEqual(len(report["missing_evidence"]), len(module.REQUIRED))
        self.assertFalse(report["release_permitted"])

    def test_boolean_claims_are_not_evidence(self):
        report = module.gate({name: {"passed": True} for name in module.REQUIRED})
        self.assertFalse(report["all_artifacts_present"])

    def test_even_all_matching_artifacts_cannot_self_approve(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate.txt"
            path.write_text("unreviewed candidate artifact")
            evidence = {
                name: dict(
                    passed=True,
                    artifact=str(path),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for name in module.REQUIRED
            }
            report = module.gate(evidence)
            self.assertTrue(report["all_artifacts_present"])
            self.assertFalse(report["release_permitted"])
            path.write_text("changed")
            self.assertFalse(module.gate(evidence)["all_artifacts_present"])
