import importlib.util
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('recovery_readiness',ROOT/'integration/recovery_readiness.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class RecoveryReadinessTests(unittest.TestCase):
    def test_empty_checkout_blocks_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=module.inventory(Path(tmp))
            self.assertFalse(report['source_complete'])
            self.assertFalse(report['release_permitted'])
            self.assertEqual(len(report['missing_source']),len(module.REQUIRED))
    def test_source_presence_is_not_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for paths in module.REQUIRED.values():
                for path in paths:
                    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('placeholder')
            report=module.inventory(root)
            self.assertTrue(report['source_complete'])
            self.assertFalse(report['release_permitted'])
