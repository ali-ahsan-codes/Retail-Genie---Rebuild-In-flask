"""Create the initial Retail Genie Main Admin using the app's validation."""

import subprocess
import sys
from pathlib import Path


ADMIN_USERNAME = "admin"
ROOT = Path(__file__).resolve().parent


def main() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flask",
            "--app",
            "wsgi",
            "create-admin",
            "--username",
            ADMIN_USERNAME,
        ],
        cwd=ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())