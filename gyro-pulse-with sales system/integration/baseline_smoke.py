"""Run with EACH app's separate Python environment. No business DB or schema writes.
Usage: python integration/baseline_smoke.py retail|gyro
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if len(sys.argv) != 2 or sys.argv[1] not in {'retail', 'gyro'}:
    raise SystemExit('Usage: baseline_smoke.py retail|gyro')
# Clear inherited connection settings; use a private in-memory SQLite connection ONLY.
# No application factory test here represents a MySQL/Android acceptance test.
os.environ.update(SECRET_KEY='baseline-only-not-for-deployment', DATABASE_URL='sqlite://',
                  MASTER_SECRET='baseline-only-master-not-for-deployment', APP_ENV='test',
                  REALTIME_DISPATCH_ENABLED='false', SESSION_COOKIE_SECURE='false')
if sys.argv[1] == 'retail':
    # Avoid loading an existing local .env.retail-genie with override=True.
    if (ROOT / 'retail-genie/.env.retail-genie').exists():
        raise SystemExit('Run smoke checks on a clean copy without .env.retail-genie; no live config was loaded.')
    sys.path.insert(0, str(ROOT / 'retail-genie'))
    from retail_genie import create_app
    app = create_app({'TESTING': True, 'REALTIME_DISPATCH_ENABLED': False})
    paths = ['/healthz', '/readyz']
else:
    sys.path.insert(0, str(ROOT / 'gyro-pulse/server'))
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    paths = ['/health']
with app.test_client() as client:
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
        print(path, response.status_code, response.get_json())
print('PASS:', sys.argv[1], 'factory / liveness; no schema initialized, no business DB accessed')
