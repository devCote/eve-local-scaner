from __future__ import annotations

import json
import sqlite3
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from paths import EXE_DIR


DAYS_BACK = 40
USER_AGENT = "EVE-Local-Intel-Scanner"
BASE_URL = "https://data.everef.net/killmails/{year}/killmails-{date}.tar.bz2"

ROOT_DIR = EXE_DIR
KILLMAILS_DIR = ROOT_DIR / "killmails"
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "local_intel.sqlite"

CYNO_MODULES = {
    21096: "Cynosural Field Generator I",
    28646: "Covert Cynosural Field Generator I",
    52694: "Industrial Cynosural Field Generator",
}

ProgressCallback = Callable[[str, int | None, int | None], None]


def report(progress_callback: ProgressCallback | None, message: str, current=None, total=None):
    print(message)

    if progress_callback:
        try:
            progress_callback(message, current, total)
        except Exception:
            pass


def utc_today():
    return datetime.now(timezone.utc).date()


def required_days(days_back: int = DAYS_BACK):
    today = utc_today()
    return [today - timedelta(days=i) for i in range(days_back)]


def archive_name_for_day(day) -> str:
    return f"killmails-{day.strftime('%Y-%m-%d')}.tar.bz2"


def archive_url_for_day(day) -> str:
    date_str = day.strftime("%Y-%m-%d")
    return BASE_URL.format(year=day.strftime("%Y"), date=date_str)


def ensure_folders():
    KILLMAILS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_archive(day, progress_callback: ProgressCallback | None = None, current=None, total=None) -> bool:
    archive_name = archive_name_for_day(day)
    archive_path = KILLMAILS_DIR / archive_name

    if archive_path.exists() and archive_path.stat().st_size > 0:
        report(progress_callback, f"[KILLMAILS] exists: {archive_name}", current, total)
        return True

    url = archive_url_for_day(day)
    tmp_path = archive_path.with_suffix(archive_path.suffix + ".part")

    report(progress_callback, f"[KILLMAILS] downloading: {archive_name}", current, total)

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/octet-stream",
            },
        )

        with urllib.request.urlopen(request, timeout=90) as response:
            content_length = int(response.headers.get("content-length", 0) or 0)
            downloaded = 0

            with tmp_path.open("wb") as f:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)

                    if content_length > 0:
                        mb_done = downloaded / 1024 / 1024
                        mb_total = content_length / 1024 / 1024
                        report(
                            progress_callback,
                            f"[KILLMAILS] downloading {archive_name}: {mb_done:.1f}/{mb_total:.1f} MB",
                            current,
                            total,
                        )

        if tmp_path.stat().st_size <= 0:
            tmp_path.unlink(missing_ok=True)
            report(progress_callback, f"[KILLMAILS] empty file skipped: {archive_name}", current, total)
            return False

        tmp_path.replace(archive_path)
        report(progress_callback, f"[KILLMAILS] downloaded: {archive_name}", current, total)
        return True

    except urllib.error.HTTPError as e:
        tmp_path.unlink(missing_ok=True)

        if e.code == 404:
            report(progress_callback, f"[KILLMAILS] not available yet: {archive_name}", current, total)
            return False

        report(progress_callback, f"[KILLMAILS] HTTP error {archive_name}: {e}", current, total)
        return False

    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        report(progress_callback, f"[KILLMAILS] download error {archive_name}: {e}", current, total)
        return False


def init_db() -> sqlite3.Connection:
    ensure_folders()

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cyno_losses (
            character_id INTEGER PRIMARY KEY,
            last_cyno_time TEXT NOT NULL,
            killmail_id INTEGER NOT NULL,
            ship_type_id INTEGER,
            cyno_module_id INTEGER NOT NULL,
            cyno_module_name TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS killmail_attackers (
            killmail_id INTEGER NOT NULL,
            killmail_time TEXT NOT NULL,
            attacker_character_id INTEGER NOT NULL,
            victim_character_id INTEGER,
            victim_ship_type_id INTEGER,
            solar_system_id INTEGER,
            final_blow INTEGER DEFAULT 0,
            damage_done INTEGER DEFAULT 0,
            PRIMARY KEY (killmail_id, attacker_character_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS archive_status (
            archive_name TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL,
            json_count INTEGER NOT NULL,
            attacker_rows INTEGER NOT NULL,
            cyno_count INTEGER NOT NULL
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attackers_character_time
        ON killmail_attackers(attacker_character_id, killmail_time DESC)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attackers_victim_time
        ON killmail_attackers(victim_character_id, killmail_time DESC)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attackers_killmail
        ON killmail_attackers(killmail_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cyno_losses_time
        ON cyno_losses(last_cyno_time)
    """)

    conn.commit()
    return conn


def archive_already_processed(conn: sqlite3.Connection, archive_name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM archive_status WHERE archive_name = ?", (archive_name,))
    return cur.fetchone() is not None


def find_cyno_module_in_item(item: dict[str, Any]):
    item_type_id = item.get("item_type_id")

    if item_type_id in CYNO_MODULES:
        return item_type_id

    for child in item.get("items", []) or []:
        found = find_cyno_module_in_item(child)
        if found:
            return found

    return None


def find_victim_cyno_module(killmail: dict[str, Any]):
    victim = killmail.get("victim", {}) or {}

    for item in victim.get("items", []) or []:
        found = find_cyno_module_in_item(item)
        if found:
            return found

    return None


def save_cyno_loss(conn: sqlite3.Connection, killmail: dict[str, Any], module_id: int) -> bool:
    victim = killmail.get("victim", {}) or {}
    character_id = victim.get("character_id")

    if not character_id:
        return False

    killmail_id = killmail.get("killmail_id")
    killmail_time = killmail.get("killmail_time")
    ship_type_id = victim.get("ship_type_id")
    module_name = CYNO_MODULES.get(module_id, str(module_id))

    if not killmail_id or not killmail_time:
        return False

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cyno_losses (
            character_id,
            last_cyno_time,
            killmail_id,
            ship_type_id,
            cyno_module_id,
            cyno_module_name
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(character_id) DO UPDATE SET
            last_cyno_time = CASE
                WHEN excluded.last_cyno_time > cyno_losses.last_cyno_time
                THEN excluded.last_cyno_time
                ELSE cyno_losses.last_cyno_time
            END,
            killmail_id = CASE
                WHEN excluded.last_cyno_time > cyno_losses.last_cyno_time
                THEN excluded.killmail_id
                ELSE cyno_losses.killmail_id
            END,
            ship_type_id = CASE
                WHEN excluded.last_cyno_time > cyno_losses.last_cyno_time
                THEN excluded.ship_type_id
                ELSE cyno_losses.ship_type_id
            END,
            cyno_module_id = CASE
                WHEN excluded.last_cyno_time > cyno_losses.last_cyno_time
                THEN excluded.cyno_module_id
                ELSE cyno_losses.cyno_module_id
            END,
            cyno_module_name = CASE
                WHEN excluded.last_cyno_time > cyno_losses.last_cyno_time
                THEN excluded.cyno_module_name
                ELSE cyno_losses.cyno_module_name
            END
    """, (
        int(character_id),
        killmail_time,
        int(killmail_id),
        ship_type_id,
        int(module_id),
        module_name,
    ))

    return True


def save_attackers(conn: sqlite3.Connection, killmail: dict[str, Any]) -> int:
    killmail_id = killmail.get("killmail_id")
    killmail_time = killmail.get("killmail_time")
    solar_system_id = killmail.get("solar_system_id")

    victim = killmail.get("victim", {}) or {}
    victim_character_id = victim.get("character_id")
    victim_ship_type_id = victim.get("ship_type_id")

    if not killmail_id or not killmail_time:
        return 0

    rows = []

    for attacker in killmail.get("attackers", []) or []:
        attacker_character_id = attacker.get("character_id")

        if not attacker_character_id:
            continue

        rows.append((
            int(killmail_id),
            killmail_time,
            int(attacker_character_id),
            victim_character_id,
            victim_ship_type_id,
            solar_system_id,
            1 if attacker.get("final_blow") else 0,
            int(attacker.get("damage_done") or 0),
        ))

    if not rows:
        return 0

    cur = conn.cursor()
    cur.executemany("""
        INSERT OR IGNORE INTO killmail_attackers (
            killmail_id,
            killmail_time,
            attacker_character_id,
            victim_character_id,
            victim_ship_type_id,
            solar_system_id,
            final_blow,
            damage_done
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    return len(rows)


def mark_archive_processed(
    conn: sqlite3.Connection,
    archive_name: str,
    json_count: int,
    attacker_rows: int,
    cyno_count: int,
):
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO archive_status (
            archive_name,
            processed_at,
            json_count,
            attacker_rows,
            cyno_count
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        archive_name,
        datetime.now(timezone.utc).isoformat(),
        int(json_count),
        int(attacker_rows),
        int(cyno_count),
    ))


def process_archive(conn: sqlite3.Connection, archive_path: Path, progress_callback: ProgressCallback | None = None, current=None, total=None) -> bool:
    if archive_already_processed(conn, archive_path.name):
        report(progress_callback, f"[LOCAL DB] already processed: {archive_path.name}", current, total)
        return False

    report(progress_callback, f"[LOCAL DB] processing: {archive_path.name}", current, total)

    json_count = 0
    attacker_rows = 0
    cyno_count = 0

    try:
        with tarfile.open(archive_path, "r:bz2") as tar:
            members = [m for m in tar if m.isfile() and m.name.endswith(".json")]
            member_total = len(members)

            for index, member in enumerate(members, start=1):
                file_obj = tar.extractfile(member)
                if not file_obj:
                    continue

                try:
                    killmail = json.load(file_obj)
                except Exception:
                    continue

                json_count += 1
                attacker_rows += save_attackers(conn, killmail)

                module_id = find_victim_cyno_module(killmail)
                if module_id:
                    if save_cyno_loss(conn, killmail, int(module_id)):
                        cyno_count += 1

                if index % 25 == 0 or index == member_total:
                    report(
                        progress_callback,
                        f"[LOCAL DB] processing {archive_path.name}: {index}/{member_total}",
                        current,
                        total,
                    )

        mark_archive_processed(
            conn=conn,
            archive_name=archive_path.name,
            json_count=json_count,
            attacker_rows=attacker_rows,
            cyno_count=cyno_count,
        )

        conn.commit()
        report(
            progress_callback,
            f"[LOCAL DB] ok: {archive_path.name} json={json_count} attackers={attacker_rows} cynos={cyno_count}",
            current,
            total,
        )
        return True

    except Exception as e:
        conn.rollback()
        report(progress_callback, f"[LOCAL DB] process error {archive_path.name}: {e}", current, total)
        return False


def cleanup_old_archives(required_names: set[str], progress_callback: ProgressCallback | None = None) -> int:
    removed = 0

    for path in KILLMAILS_DIR.glob("killmails-*.tar.bz2"):
        if path.name not in required_names:
            try:
                path.unlink()
                removed += 1
                report(progress_callback, f"[KILLMAILS] removed old archive: {path.name}")
            except Exception as e:
                report(progress_callback, f"[KILLMAILS] remove error {path.name}: {e}")

    return removed


def cleanup_old_db_rows(conn: sqlite3.Connection, required_names: set[str], days, progress_callback: ProgressCallback | None = None) -> int:
    if not days:
        return 0

    oldest = min(days)
    cutoff = f"{oldest.strftime('%Y-%m-%d')}T00:00:00Z"

    cur = conn.cursor()

    cur.execute("DELETE FROM killmail_attackers WHERE killmail_time < ?", (cutoff,))
    removed_attackers = cur.rowcount if cur.rowcount is not None else 0

    cur.execute("DELETE FROM cyno_losses WHERE last_cyno_time < ?", (cutoff,))
    removed_cynos = cur.rowcount if cur.rowcount is not None else 0

    if required_names:
        placeholders = ",".join("?" for _ in required_names)
        cur.execute(
            f"DELETE FROM archive_status WHERE archive_name NOT IN ({placeholders})",
            tuple(sorted(required_names)),
        )
    else:
        cur.execute("DELETE FROM archive_status")

    removed_status = cur.rowcount if cur.rowcount is not None else 0

    conn.commit()

    total = int(removed_attackers) + int(removed_cynos) + int(removed_status)

    if total:
        report(
            progress_callback,
            "[LOCAL DB] cleanup: "
            f"attackers={removed_attackers}, cynos={removed_cynos}, archives={removed_status}",
        )

    return total


def ensure_local_intel_ready(days_back: int = DAYS_BACK, progress_callback: ProgressCallback | None = None) -> dict[str, int]:
    """Startup updater with progress callback.

    progress_callback(message, current, total)
    """
    ensure_folders()

    days = required_days(days_back)
    required_names = {archive_name_for_day(day) for day in days}

    total_steps = len(days) * 2 + 3
    step = 0

    report(progress_callback, "[LOCAL DB] checking killmail archives...", step, total_steps)

    for day in days:
        step += 1
        download_archive(day, progress_callback, step, total_steps)

    step += 1
    report(progress_callback, "[LOCAL DB] opening SQLite database...", step, total_steps)
    conn = init_db()

    processed = 0

    try:
        step += 1
        report(progress_callback, "[LOCAL DB] cleaning old data...", step, total_steps)
        cleanup_old_archives(required_names, progress_callback)
        cleanup_old_db_rows(conn, required_names, days, progress_callback)

        for day in sorted(days):
            step += 1
            archive_path = KILLMAILS_DIR / archive_name_for_day(day)

            if not archive_path.exists():
                report(progress_callback, f"[LOCAL DB] archive missing, skipped: {archive_path.name}", step, total_steps)
                continue

            if process_archive(conn, archive_path, progress_callback, step, total_steps):
                processed += 1

        step = total_steps
        report(progress_callback, f"[LOCAL DB] ready. processed={processed}", step, total_steps)

        return {
            "processed": processed,
            "days": len(days),
            "total_steps": total_steps,
        }

    finally:
        conn.close()


if __name__ == "__main__":
    ensure_local_intel_ready()
