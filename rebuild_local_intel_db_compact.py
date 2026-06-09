from __future__ import annotations

from pathlib import Path

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
