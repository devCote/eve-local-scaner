from __future__ import annotations
# Allow running this script from tools/ while importing runtime modules from project root.
from pathlib import Path as _Path
import sys as _sys
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))



import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paths import user_data_path


DAYS_BACK = 40
DB_PATH = user_data_path(Path("data") / "local_intel.sqlite")


def bytes_to_mb(value: int) -> float:
    return value / 1024 / 1024


def required_archive_names(days_back: int = DAYS_BACK) -> set[str]:
    today = datetime.now(timezone.utc).date()
    return {
        f"killmails-{(today - timedelta(days=i)).strftime('%Y-%m-%d')}.tar.bz2"
        for i in range(days_back)
    }


def compact_local_intel_db(days_back: int = DAYS_BACK) -> None:
    if not DB_PATH.exists():
        print(f"[COMPACT] DB not found: {DB_PATH}")
        return

    before = DB_PATH.stat().st_size
    print(f"[COMPACT] DB: {DB_PATH}")
    print(f"[COMPACT] before: {bytes_to_mb(before):.2f} MB")

    today = datetime.now(timezone.utc).date()
    oldest = today - timedelta(days=days_back - 1)
    cutoff = f"{oldest.strftime('%Y-%m-%d')}T00:00:00Z"
    archive_names = required_archive_names(days_back)

    conn = sqlite3.connect(str(DB_PATH), timeout=60)

    try:
        cur = conn.cursor()

        cur.execute("PRAGMA journal_mode=DELETE")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA temp_store=MEMORY")

        cur.execute("DELETE FROM killmail_attackers WHERE killmail_time < ?", (cutoff,))
        removed_attackers = cur.rowcount if cur.rowcount is not None else 0

        cur.execute("DELETE FROM cyno_losses WHERE last_cyno_time < ?", (cutoff,))
        removed_cynos = cur.rowcount if cur.rowcount is not None else 0

        if archive_names:
            placeholders = ",".join("?" for _ in archive_names)
            cur.execute(
                f"DELETE FROM archive_status WHERE archive_name NOT IN ({placeholders})",
                tuple(sorted(archive_names)),
            )
            removed_archives = cur.rowcount if cur.rowcount is not None else 0
        else:
            removed_archives = 0

        conn.commit()

        print(
            "[COMPACT] removed old rows: "
            f"attackers={removed_attackers}, cynos={removed_cynos}, archives={removed_archives}"
        )

        print("[COMPACT] optimizing...")
        cur.execute("PRAGMA optimize")
        conn.commit()

        # Important: DELETE does not shrink SQLite file. VACUUM rewrites the DB and returns free pages to disk.
        print("[COMPACT] vacuuming... this can take a few minutes")
        cur.execute("VACUUM")
        conn.commit()

    finally:
        conn.close()

    after = DB_PATH.stat().st_size
    saved = max(0, before - after)

    print(f"[COMPACT] after: {bytes_to_mb(after):.2f} MB")
    print(f"[COMPACT] saved: {bytes_to_mb(saved):.2f} MB")


if __name__ == "__main__":
    compact_local_intel_db()
