"""Offline, dependency-free source/isolation checks. No app imports or DB connections."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent


class FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / 'docs/SOURCE_MANIFEST.json').read_text())
        cls.recovery_overlays = json.loads((ROOT / 'docs/RECOVERY_2A_MANIFEST.json').read_text())['files']
        cls.phase2b_overlays = json.loads((ROOT / 'docs/PHASE_2B_MANIFEST.json').read_text())['files']
        cls.phase3_overlays = json.loads((ROOT / 'docs/PHASE_3_MANIFEST.json').read_text())['files']
        cls.phase4_overlays = json.loads((ROOT / 'docs/PHASE_4_MANIFEST.json').read_text())['files']
        cls.phase5_overlays = json.loads((ROOT / 'docs/PHASE_5_MANIFEST.json').read_text())['files']
        cls.phase6_overlays = json.loads((ROOT / 'docs/PHASE_6_7_MANIFEST.json').read_text())['files']
        cls.overlays = {**cls.recovery_overlays, **cls.phase2b_overlays, **cls.phase3_overlays, **cls.phase4_overlays, **cls.phase5_overlays, **cls.phase6_overlays}

    def test_original_sources_unchanged(self):
        for item in self.manifest['files']:
            with self.subTest(path=item['source']):
                self.assertEqual(hashlib.sha256((REPO / item['source']).read_bytes()).hexdigest(), item['source_sha256'])

    def test_copy_integrity(self):
        for item in self.manifest['files']:
            with self.subTest(path=item['copy']):
                self.assertEqual(hashlib.sha256((ROOT / item['copy']).read_bytes()).hexdigest(), self.overlays.get(item['copy'], {}).get('sha256', item['copy_sha256']))

    def test_recovery_overlay_integrity(self):
        # Verify the entire immutable evidence chain, not rewritten earlier manifests.
        previous={item['copy']:item['copy_sha256'] for item in self.manifest['files']}
        for index,layer in enumerate([self.recovery_overlays,self.phase2b_overlays,self.phase3_overlays,self.phase4_overlays,self.phase5_overlays,self.phase6_overlays]):
            for name,entry in layer.items():
                if index>0:self.assertEqual(entry.get('previous_sha256'),previous.get(name))
                elif 'baseline_sha256' in entry:self.assertEqual(entry['baseline_sha256'],previous.get(name))
                previous[name]=entry['sha256']

    def test_current_overlay_integrity(self):
        for name,entry in self.overlays.items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),entry['sha256'])
                if name.endswith('.py'):ast.parse((ROOT/name).read_text())

    def test_contract_mirrors_and_prior_hashes(self):
        self.assertEqual((ROOT/'gyro-pulse/server/integration_contract.py').read_bytes(),
                         (ROOT/'retail-genie/retail_genie/integration_contract.py').read_bytes())
        self.assertEqual((ROOT/'gyro-pulse/server/sync_core.py').read_text().replace('from models import db','from .extensions import db'),
                         (ROOT/'retail-genie/retail_genie/sync_core.py').read_text())
        self.assertEqual((ROOT/'gyro-pulse/server/catalog_contract.py').read_bytes(),
                         (ROOT/'retail-genie/retail_genie/catalog_contract.py').read_bytes())
        self.assertEqual((ROOT/'gyro-pulse/server/order_contract.py').read_text().replace('from catalog_contract import','from .catalog_contract import'),
                         (ROOT/'retail-genie/retail_genie/order_contract.py').read_text())
        self.assertEqual((ROOT/'gyro-pulse/server/mobile_crypto.py').read_text().replace('from integration_contract import','from .integration_contract import').replace('from order_contract import','from .order_contract import'),
                         (ROOT/'retail-genie/retail_genie/mobile_crypto.py').read_text())
        baseline={item['copy']:item['copy_sha256'] for item in self.manifest['files']}
        previous={**baseline, **{name:entry['sha256'] for name,entry in self.recovery_overlays.items()}}
        for name,entry in self.phase2b_overlays.items():
            self.assertEqual(entry.get('previous_sha256'),previous.get(name))

    def test_python_syntax(self):
        for item in self.manifest['files']:
            if item['copy'].endswith('.py'):
                with self.subTest(path=item['copy']):
                    ast.parse((ROOT / item['copy']).read_text(encoding='utf-8'), filename=item['copy'])

    def test_no_runtime_artifacts_copied(self):
        forbidden = {'.env', '.env.retail-genie', 'local.properties'}
        for item in self.manifest['files']:
            path = Path(item['copy'])
            self.assertNotIn(path.name, forbidden)
            self.assertFalse({'uploads', 'instance', '__pycache__', '.gradle', 'build', 'preview'} & set(path.parts))
            self.assertFalse(str(path).startswith('gyro-pulse/server/backups/'))
            self.assertNotIn(path.suffix, {'.db', '.sqlite', '.jks', '.keystore'})

    def test_retail_installer_database_isolated(self):
        setup = (ROOT / 'retail-genie/scripts/setup_database.py').read_text()
        schema = (ROOT / 'retail-genie/database-schema.sql').read_text()
        self.assertIn('DATABASE_NAME = "retail_genie_hybrid"', setup)
        self.assertIn('APP_USERNAME = "retail_genie_hybrid_app"', setup)
        self.assertNotIn('`retail_genie`', setup)
        self.assertIn('USE retail_genie_hybrid;', schema)
        self.assertNotIn('USE retail_genie;', schema)

    def test_separate_ports_and_database_templates(self):
        retail = (ROOT / 'retail-genie/.env.example').read_text()
        gyro = (ROOT / 'gyro-pulse/server/.env.example').read_text()
        self.assertIn('FLASK_PORT=5100', retail)
        self.assertIn('/retail_genie_hybrid?', retail)
        self.assertIn('PORT=5200', gyro)
        self.assertIn('gyro_pulse_hybrid.db', gyro)
        config = json.loads((ROOT / 'gyro-pulse/server/config.json').read_text())
        self.assertNotIn('admin', config)

    def test_integration_not_enabled(self):
        config = json.loads((ROOT / 'integration/phase-status.json').read_text())
        self.assertEqual(config['implemented_phase'], 1)
        self.assertFalse(config['connector_enabled'])
        self.assertFalse(config['production_ready'])


if __name__ == '__main__':
    unittest.main()
