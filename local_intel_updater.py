from __future__ import annotations

import json
import time
import sqlite3
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from paths import USER_DATA_DIR, ensure_user_data_dirs


DAYS_BACK = 40
SCHEMA_VERSION = 2

USER_AGENT = "EVE-Local-Intel-Scanner"
BASE_URL = "https://data.everef.net/killmails/{year}/killmails-{date}.tar.bz2"

ROOT_DIR = USER_DATA_DIR
KILLMAILS_DIR = ROOT_DIR / "killmails"
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "local_intel.sqlite"
UNAVAILABLE_ARCHIVES_PATH = ROOT_DIR / "unavailable_archives.json"
UNAVAILABLE_TTL_SECONDS = 4 * 60 * 60  # 4 hours

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
    ensure_user_data_dirs()
    KILLMAILS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)




def load_unavailable_archive_cache() -> dict:
    try:
        if not UNAVAILABLE_ARCHIVES_PATH.exists():
            return {}

        with UNAVAILABLE_ARCHIVES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


def save_unavailable_archive_cache(data: dict) -> None:
    try:
        UNAVAILABLE_ARCHIVES_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = UNAVAILABLE_ARCHIVES_PATH.with_suffix(UNAVAILABLE_ARCHIVES_PATH.suffix + ".tmp")

        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        tmp.replace(UNAVAILABLE_ARCHIVES_PATH)

    except Exception as e:
        print(f"[KILLMAILS] unavailable cache save error: {e}")


def unavailable_cache_get(archive_name: str) -> dict | None:
    data = load_unavailable_archive_cache()
    item = data.get(archive_name)

    if not isinstance(item, dict):
        return None

    checked_at = float(item.get("checked_at", 0) or 0)

    if time.time() - checked_at > UNAVAILABLE_TTL_SECONDS:
        data.pop(archive_name, None)
        save_unavailable_archive_cache(data)
        return None

    return item


def unavailable_cache_set(archive_name: str, reason: str = "404") -> None:
    data = load_unavailable_archive_cache()
    data[archive_name] = {
        "checked_at": time.time(),
        "reason": str(reason),
    }
    save_unavailable_archive_cache(data)


def unavailable_cache_clear(archive_name: str) -> None:
    data = load_unavailable_archive_cache()

    if archive_name in data:
        data.pop(archive_name, None)
        save_unavailable_archive_cache(data)


def unavailable_cache_prune(required_names: set[str]) -> None:
    data = load_unavailable_archive_cache()

    if not data:
        return

    now = time.time()
    changed = False

    for archive_name, item in list(data.items()):
        checked_at = 0

        if isinstance(item, dict):
            checked_at = float(item.get("checked_at", 0) or 0)

        if archive_name not in required_names or now - checked_at > UNAVAILABLE_TTL_SECONDS:
            data.pop(archive_name, None)
            changed = True

    if changed:
        save_unavailable_archive_cache(data)


def download_archive(day, progress_callback: ProgressCallback | None = None, current=None, total=None) -> bool:
    archive_name = archive_name_for_day(day)
    archive_path = KILLMAILS_DIR / archive_name

    if archive_path.exists() and archive_path.stat().st_size > 0:
        unavailable_cache_clear(archive_name)
        report(progress_callback, f"[KILLMAILS] exists: {archive_name}", current, total)
        return True

    recent_404 = unavailable_cache_get(archive_name)
    if recent_404:
        age_min = int((time.time() - float(recent_404.get("checked_at", 0) or 0)) / 60)
        ttl_min = int(UNAVAILABLE_TTL_SECONDS / 60)
        report(progress_callback, f"[KILLMAILS] skipped recent 404 cache: {archive_name} ({age_min}/{ttl_min} min)", current, total)
        return False

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
        unavailable_cache_clear(archive_name)
        report(progress_callback, f"[KILLMAILS] downloaded: {archive_name}", current, total)
        return True

    except urllib.error.HTTPError as e:
        tmp_path.unlink(missing_ok=True)

        if e.code == 404:
            unavailable_cache_set(archive_name, "404")
            report(progress_callback, f"[KILLMAILS] not available yet, cached for 4h: {archive_name}", current, total)
            return False

        report(progress_callback, f"[KILLMAILS] HTTP error {archive_name}: {e}", current, total)
        return False

    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        report(progress_callback, f"[KILLMAILS] download error {archive_name}: {e}", current, total)
        return False


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        return {str(row[1]) for row in cur.fetchall()}
    except Exception:
        return set()


def is_old_flat_schema(conn: sqlite3.Connection) -> bool:
    cols = table_columns(conn, "killmail_attackers")
    return "killmail_time" in cols or "victim_character_id" in cols or "victim_ship_type_id" in cols


def rebuild_schema(conn: sqlite3.Connection, progress_callback: ProgressCallback | None = None):
    report(progress_callback, "[LOCAL DB] old schema detected, rebuilding compact DB...")

    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS killmail_attackers")
    cur.execute("DROP TABLE IF EXISTS killmails")
    cur.execute("DROP TABLE IF EXISTS cyno_losses")
    cur.execute("DROP TABLE IF EXISTS archive_status")
    cur.execute("PRAGMA user_version = 0")
    conn.commit()

    create_schema(conn)
    conn.commit()


def create_schema(conn: sqlite3.Connection):
    cur = conn.cursor()

    # One row per killmail. Victim/system/time are no longer repeated for every attacker.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS killmails (
            killmail_id INTEGER PRIMARY KEY,
            killmail_time TEXT NOT NULL,
            victim_character_id INTEGER,
            victim_ship_type_id INTEGER,
            solar_system_id INTEGER
        )
    """)

    # One row per attacker only. Smaller and faster than storing killmail data on every row.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS killmail_attackers (
            killmail_id INTEGER NOT NULL,
            attacker_character_id INTEGER NOT NULL,
            final_blow INTEGER DEFAULT 0,
            damage_done INTEGER DEFAULT 0,
            PRIMARY KEY (killmail_id, attacker_character_id)
        )
    """)

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
        CREATE TABLE IF NOT EXISTS archive_status (
            archive_name TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL,
            json_count INTEGER NOT NULL,
            attacker_rows INTEGER NOT NULL,
            cyno_count INTEGER NOT NULL
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_killmails_time
        ON killmails(killmail_time DESC)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_killmails_victim_time
        ON killmails(victim_character_id, killmail_time DESC)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attackers_character_killmail
        ON killmail_attackers(attacker_character_id, killmail_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attackers_killmail
        ON killmail_attackers(killmail_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cyno_losses_time
        ON cyno_losses(last_cyno_time)
    """)

    cur.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def init_db(progress_callback: ProgressCallback | None = None) -> sqlite3.Connection:
    ensure_folders()

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    
    try:
        cur = conn.cursor()

        cur.execute("PRAGMA user_version")
        version = int(cur.fetchone()[0] or 0)

        if is_old_flat_schema(conn) or (version and version < SCHEMA_VERSION):
            rebuild_schema(conn, progress_callback)
        else:
            create_schema(conn)
            cur.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()

        return conn
    except Exception:
        conn.close()
        raise


def archive_already_processed(conn: sqlite3.Connection, archive_name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM archive_status WHERE archive_name = ?", (archive_name,))
    return cur.fetchone() is not None


def find_cyno_module_in_item(item: dict[str, Any]):
    item_type_id = item.get("item_type_id")

    if item_type_id in CYNO_MODULES:
        return item_type_id

    children = item.get("items", []) or []
    if not isinstance(children, list):
        return None
    
    for child in children:
        if not isinstance(child, dict):
            continue
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


def save_killmail(conn: sqlite3.Connection, killmail: dict[str, Any]) -> bool:
    killmail_id = killmail.get("killmail_id")
    killmail_time = killmail.get("killmail_time")
    solar_system_id = killmail.get("solar_system_id")

    victim = killmail.get("victim", {}) or {}
    victim_character_id = victim.get("character_id")
    victim_ship_type_id = victim.get("ship_type_id")

    if not killmail_id or not killmail_time:
        return False

    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO killmails (
            killmail_id,
            killmail_time,
            victim_character_id,
            victim_ship_type_id,
            solar_system_id
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        int(killmail_id),
        killmail_time,
        victim_character_id,
        victim_ship_type_id,
        solar_system_id,
    ))

    return True


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

    if not killmail_id:
        return 0

    rows = []

    for attacker in killmail.get("attackers", []) or []:
        attacker_character_id = attacker.get("character_id")

        if not attacker_character_id:
            continue

        rows.append((
            int(killmail_id),
            int(attacker_character_id),
            1 if attacker.get("final_blow") else 0,
            int(attacker.get("damage_done") or 0),
        ))

    if not rows:
        return 0

    cur = conn.cursor()
    cur.executemany("""
        INSERT OR IGNORE INTO killmail_attackers (
            killmail_id,
            attacker_character_id,
            final_blow,
            damage_done
        )
        VALUES (?, ?, ?, ?)
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

                if not save_killmail(conn, killmail):
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
        
        # Delete archive file after successful processing to free disk space
        try:
            archive_path.unlink()
            report(
                progress_callback,
                f"[LOCAL DB] archived and deleted: {archive_path.name}",
                current,
                total,
            )
        except Exception as e:
            report(progress_callback, f"[LOCAL DB] delete archive error {archive_path.name}: {e}", current, total)
        
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

    # Killmails delete cascades logically by first deleting attacker rows for old killmails.
    cur.execute("""
        DELETE FROM killmail_attackers
        WHERE killmail_id IN (
            SELECT killmail_id FROM killmails WHERE killmail_time < ?
        )
    """, (cutoff,))
    removed_attackers = cur.rowcount if cur.rowcount is not None else 0

    cur.execute("DELETE FROM killmails WHERE killmail_time < ?", (cutoff,))
    removed_killmails = cur.rowcount if cur.rowcount is not None else 0

    cur.execute("DELETE FROM cyno_losses WHERE last_cyno_time < ?", (cutoff,))
    removed_cynos = cur.rowcount if cur.rowcount is not None else 0

    if required_names:
        placeholders = ",".join("?" for _ in required_names)
        cur.execute(
            f"DELETE FROM archive_status WHERE archive_name NOT IN ({placeholders})",
            tuple(sorted(required_names)),
        )
        removed_archives = cur.rowcount if cur.rowcount is not None else 0
    else:
        removed_archives = 0

    conn.commit()

    total = int(removed_attackers) + int(removed_killmails) + int(removed_cynos) + int(removed_archives)

    if total:
        report(
            progress_callback,
            "[LOCAL DB] cleanup: "
            f"killmails={removed_killmails}, attackers={removed_attackers}, "
            f"cynos={removed_cynos}, archives={removed_archives}",
        )

    return total


def compact_database(conn: sqlite3.Connection, progress_callback: ProgressCallback | None = None) -> None:
    try:
        report(progress_callback, "[LOCAL DB] compacting SQLite database...")
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=DELETE")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA optimize")
        conn.commit()

        cur.execute("VACUUM")
        conn.commit()

        if DB_PATH.exists():
            size_mb = DB_PATH.stat().st_size / 1024 / 1024
            report(progress_callback, f"[LOCAL DB] compacted. size={size_mb:.1f} MB")

    except Exception as e:
        report(progress_callback, f"[LOCAL DB] compact skipped: {e}")



def get_processed_archive_names(conn: sqlite3.Connection) -> set[str]:
    try:
        cur = conn.cursor()
        cur.execute("SELECT archive_name FROM archive_status")
        return {str(row[0]) for row in cur.fetchall()}
    except Exception:
        return set()


def get_unprocessed_archives(conn: sqlite3.Connection, days) -> list[Path]:
    processed = get_processed_archive_names(conn)
    result = []

    for day in sorted(days):
        archive_path = KILLMAILS_DIR / archive_name_for_day(day)

        if archive_path.exists() and archive_path.name not in processed:
            result.append(archive_path)

    return result


def get_missing_days(days) -> list:
    """Find days that need to be downloaded.
    
    A day is considered "missing" if:
    - Archive file doesn't exist on disk AND
    - Archive hasn't been processed (not in archive_status table)
    
    This way if archive was downloaded and processed, we don't re-download
    even if the .tar.bz2 file was deleted to save disk space.
    """
    result = []

    for day in days:
        archive_path = KILLMAILS_DIR / archive_name_for_day(day)

        # If file exists, no need to download
        if archive_path.exists() and archive_path.stat().st_size > 0:
            continue
        
        # If file doesn't exist but was already processed, skip download
        # (it means we deleted it after processing - intentional)
        archive_name = archive_name_for_day(day)
        if archive_was_processed(archive_name):
            continue
        
        # File missing AND not processed before = need to download
        result.append(day)

    return result


def archive_was_processed(archive_name: str) -> bool:
    """Check if an archive was already processed and added to DB.
    
    This is recorded in archive_status table when process_archive() succeeds.
    Used to avoid re-downloading archives that we intentionally deleted
    after processing them to save disk space.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return False
    
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM archive_status WHERE archive_name = ? LIMIT 1",
            (archive_name,),
        )
        result = cur.fetchone() is not None
        conn.close()
        return result
    except Exception:
        return False


def database_has_recent_window(conn: sqlite3.Connection, required_names: set[str]) -> bool:
    processed = get_processed_archive_names(conn)

    if not required_names:
        return False

    return required_names.issubset(processed)


def ensure_local_intel_ready(days_back: int = DAYS_BACK, progress_callback: ProgressCallback | None = None) -> dict[str, int]:
    ensure_folders()

    days = required_days(days_back)
    required_names = {archive_name_for_day(day) for day in days}
    unavailable_cache_prune(required_names)

    report(progress_callback, "[1/4] Checking local SQLite database...", 2, 100)
    conn = init_db(progress_callback)

    processed_archives = 0

    try:
        missing_days = get_missing_days(days)
        unprocessed_archives = get_unprocessed_archives(conn, days)

        if not missing_days and not unprocessed_archives and database_has_recent_window(conn, required_names):
            report(progress_callback, "[4/4] Local intel database is ready. Opening app...", 100, 100)
            return {
                "processed": 0,
                "downloaded": 0,
                "days": len(days),
                "total_steps": 1,
            }

        downloaded = 0

        # Phase 2: downloads use 5-45%
        download_total = max(1, len(missing_days))

        if missing_days:
            report(progress_callback, f"[2/4] Downloading missing archives: {len(missing_days)}", 5, 100)

        for index, day in enumerate(missing_days, start=1):
            archive_name = archive_name_for_day(day)
            percent = 5 + int((index - 1) / download_total * 40)
            report(progress_callback, f"[2/4] Downloading {index}/{len(missing_days)}: {archive_name}", percent, 100)

            ok = download_archive(day, progress_callback=None)

            if ok:
                downloaded += 1
                status = "Downloaded"
            else:
                status = "Skipped / not available yet"

            percent = 5 + int(index / download_total * 40)
            report(progress_callback, f"[2/4] {status} {index}/{len(missing_days)}", percent, 100)

        # Phase 3: cleanup
        report(progress_callback, "[3/4] Cleaning old local data...", 48, 100)
        cleanup_old_archives(required_names, progress_callback)
        cleanup_old_db_rows(conn, required_names, days, progress_callback)

        # Recalculate after downloads and cleanup.
        unprocessed_archives = get_unprocessed_archives(conn, days)
        process_total = max(1, len(unprocessed_archives))

        if unprocessed_archives:
            report(progress_callback, f"[3/4] Adding archives to SQLite: {len(unprocessed_archives)}", 52, 100)
        else:
            report(progress_callback, "[3/4] No new archives to add to SQLite.", 80, 100)

        # Processing uses 52-88%
        for index, archive_path in enumerate(unprocessed_archives, start=1):
            percent = 52 + int((index - 1) / process_total * 36)
            report(progress_callback, f"[3/4] Adding to SQLite {index}/{len(unprocessed_archives)}: {archive_path.name}", percent, 100)

            if process_archive(conn, archive_path, progress_callback=None):
                processed_archives += 1

            percent = 52 + int(index / process_total * 36)
            report(progress_callback, f"[3/4] Added to SQLite {index}/{len(unprocessed_archives)}", percent, 100)

        # Phase 4: compact only if changed. Keep under 100 until really finished.
        if downloaded or processed_archives:
            report(progress_callback, "[4/4] Optimizing SQLite database...", 92, 100)
            compact_database(conn, progress_callback=None)

        report(
            progress_callback,
            f"[4/4] Local intel database is ready. downloaded={downloaded}, processed={processed_archives}. Opening app...",
            100,
            100,
        )

        return {
            "processed": processed_archives,
            "downloaded": downloaded,
            "days": len(days),
            "total_steps": 100,
        }

    finally:
        conn.close()

