from __future__ import annotations
# Allow running this script from tools/ while importing runtime modules from project root.
from pathlib import Path as _Path
import sys as _sys
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))




from local_intel_updater import (
    DB_PATH,
    ensure_local_intel_ready,
)


def main():
    if DB_PATH.exists():
        print(f"[REBUILD] deleting old DB: {DB_PATH}")
        DB_PATH.unlink()

    ensure_local_intel_ready()


if __name__ == "__main__":
    main()
