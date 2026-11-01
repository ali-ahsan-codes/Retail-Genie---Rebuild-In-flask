"""Keep all isolated native test imports away from inherited/live database settings."""

import os
import sys
from pathlib import Path

NATIVE_ROOT = Path(__file__).resolve().parents[1]
if (NATIVE_ROOT / ".env.retail-genie").exists():
    raise RuntimeError("Run isolated tests without a live .env.retail-genie file")
sys.path.insert(0, str(NATIVE_ROOT))
os.environ.update(
    SECRET_KEY="native-tests-only-" + "x" * 32,
    DATABASE_URL="sqlite://",
    REALTIME_DISPATCH_ENABLED="false",
    APP_ENV="test",
)
