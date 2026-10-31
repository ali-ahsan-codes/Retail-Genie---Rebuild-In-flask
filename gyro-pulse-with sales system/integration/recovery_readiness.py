"""Current-checkout recovery inventory. Missing source is a blocker, not a passed phase.
No DB/network/schema writes or runtime configuration loading.
"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    '2B_pairing': ['gyro-pulse/server/integration_api.py', 'retail-genie/retail_genie/field_integration.py'],
    '3_transport': ['gyro-pulse/server/sync_core.py', 'retail-genie/retail_genie/sync_core.py'],
    '4_catalog': ['gyro-pulse/server/catalog_bridge.py', 'retail-genie/retail_genie/field_catalog.py'],
    '5_native_orders': ['gyro-pulse/server/field_orders.py', 'retail-genie/retail_genie/field_orders.py'],
    '6_mobile': ['gyro-pulse/server/field_mobile.py', 'retail-genie/retail_genie/field_mobile.py',
                 'gyro-pulse/android/app/src/main/java/com/example/hybrid/HybridEngine.kt'],
    '7_acceptance_tooling': ['integration/release_gate.py','retail-genie/retail_genie/field_audit.py'],
}

def inventory(root=ROOT):
    missing = {phase: [name for name in files if not (root/name).is_file()] for phase,files in REQUIRED.items()}
    missing = {phase: files for phase,files in missing.items() if files}
    return dict(schema_version=1, source_complete=not missing, release_permitted=False,
                missing_source=missing,
                note='File presence alone does not establish implementation correctness or MySQL/Android/UAT acceptance.')

if __name__ == '__main__':
    result=inventory()
    print(json.dumps(result,indent=2))
    raise SystemExit(1 if not result['source_complete'] else 0)
