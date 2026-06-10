from __future__ import annotations

import sqlite3
from pathlib import Path

from paths import USER_DATA_DIR, user_data_path
from local_intel_db import get_db_path


def format_size(path: Path) -> str:
    try:
        if not path.exists():
            return "missing"

        size = path.stat().st_size

        if size >= 1024 * 1024 * 1024:
            return f"{size / 1024 / 1024 / 1024:.2f} GB"

        if size >= 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"

        if size >= 1024:
            return f"{size / 1024:.1f} KB"

        return f"{size} B"

    except Exception as e:
        return f"error: {e}"


def sqlite_scalar(db_path: Path, query: str, default="-"):
    try:
        if not db_path.exists():
            return default

        conn = sqlite3.connect(str(db_path), timeout=10)

        try:
            cur = conn.cursor()
            cur.execute(query)
            row = cur.fetchone()

            if not row:
                return default

            return row[0] if row[0] is not None else default

        finally:
            conn.close()

    except Exception:
        return default


def get_last_processed_archive(db_path: Path) -> str:
    try:
        if not db_path.exists():
            return "-"

        conn = sqlite3.connect(str(db_path), timeout=10)

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT archive_name
                FROM archive_status
                ORDER BY archive_name DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return str(row[0]) if row else "-"

        finally:
            conn.close()

    except Exception:
        return "-"


def collect_health_info() -> str:
    db_path = get_db_path()
    killmails_dir = user_data_path("killmails")
    logs_dir = user_data_path("logs")
    cache_path = user_data_path("cache.json")
    unavailable_cache_path = user_data_path("unavailable_archives.json")

    archives = sorted(killmails_dir.glob("killmails-*.tar.bz2")) if killmails_dir.exists() else []
    logs = sorted(logs_dir.glob("*.log")) if logs_dir.exists() else []

    killmail_count = sqlite_scalar(db_path, "SELECT COUNT(*) FROM killmails", default="-")
    attacker_count = sqlite_scalar(db_path, "SELECT COUNT(*) FROM killmail_attackers", default="-")
    archive_status_count = sqlite_scalar(db_path, "SELECT COUNT(*) FROM archive_status", default="-")
    last_archive = get_last_processed_archive(db_path)

    lines = [
        "EVE Local Intel Scanner — Health Check",
        "",
        f"User data:",
        f"  {USER_DATA_DIR}",
        "",
        f"Database:",
        f"  Path: {db_path}",
        f"  Exists: {'yes' if db_path.exists() else 'no'}",
        f"  Size: {format_size(db_path)}",
        f"  Killmails: {killmail_count}",
        f"  Attackers: {attacker_count}",
        f"  Processed archives in DB: {archive_status_count}",
        f"  Last processed archive: {last_archive}",
        "",
        f"Archives:",
        f"  Folder: {killmails_dir}",
        f"  Files: {len(archives)}",
        f"  Total size: {sum(p.stat().st_size for p in archives if p.exists()) / 1024 / 1024:.1f} MB" if archives else "  Total size: 0 MB",
        "",
        f"Logs:",
        f"  Folder: {logs_dir}",
        f"  Files: {len(logs)}",
        "",
        f"Cache:",
        f"  cache.json: {cache_path} ({format_size(cache_path)})",
        f"  unavailable_archives.json: {unavailable_cache_path} ({format_size(unavailable_cache_path)})",
    ]

    return "\n".join(lines)
