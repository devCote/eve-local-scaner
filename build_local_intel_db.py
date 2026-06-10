import json
import sqlite3
import tarfile
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
KILLMAILS_DIR = ROOT_DIR / "killmails"
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "local_intel.sqlite"


CYNO_MODULES = {
    21096: "Cynosural Field Generator I",
    28646: "Covert Cynosural Field Generator I",
    52694: "Industrial Cynosural Field Generator",
}


def init_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
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
    cur.execute(
        "SELECT 1 FROM archive_status WHERE archive_name = ?",
        (archive_name,),
    )
    return cur.fetchone() is not None


def find_cyno_module_in_item(item: dict):
    item_type_id = item.get("item_type_id")

    if item_type_id in CYNO_MODULES:
        return item_type_id

    for child in item.get("items", []):
        found = find_cyno_module_in_item(child)
        if found:
            return found

    return None


def find_victim_cyno_module(killmail: dict):
    victim = killmail.get("victim", {})
    for item in victim.get("items", []):
        found = find_cyno_module_in_item(item)
        if found:
            return found
    return None


def save_cyno_loss(conn, killmail: dict, module_id: int):
    victim = killmail.get("victim", {})
    character_id = victim.get("character_id")

    if not character_id:
        return False

    killmail_id = killmail.get("killmail_id")
    killmail_time = killmail.get("killmail_time")
    ship_type_id = victim.get("ship_type_id")
    module_name = CYNO_MODULES[module_id]

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
        character_id,
        killmail_time,
        killmail_id,
        ship_type_id,
        module_id,
        module_name,
    ))

    return True


def save_attackers(conn, killmail: dict) -> int:
    killmail_id = killmail.get("killmail_id")
    killmail_time = killmail.get("killmail_time")
    solar_system_id = killmail.get("solar_system_id")

    victim = killmail.get("victim", {})
    victim_character_id = victim.get("character_id")
    victim_ship_type_id = victim.get("ship_type_id")

    if not killmail_id or not killmail_time:
        return 0

    rows = []

    for attacker in killmail.get("attackers", []):
        attacker_character_id = attacker.get("character_id")

        if not attacker_character_id:
            continue

        rows.append((
            killmail_id,
            killmail_time,
            attacker_character_id,
            victim_character_id,
            victim_ship_type_id,
            solar_system_id,
            1 if attacker.get("final_blow") else 0,
            attacker.get("damage_done", 0),
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


def mark_archive_processed(conn, archive_name: str, json_count: int, attacker_rows: int, cyno_count: int):
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
        json_count,
        attacker_rows,
        cyno_count,
    ))


def process_archive(conn, archive_path: Path):
    if archive_already_processed(conn, archive_path.name):
        print(f"[SKIP] already processed: {archive_path.name}")
        return

    print(f"\n[PROCESS] {archive_path.name}")

    json_count = 0
    attacker_rows = 0
    cyno_count = 0

    try:
        with tarfile.open(archive_path, "r:bz2") as tar:
            for member in tar:
                if not member.isfile() or not member.name.endswith(".json"):
                    continue

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
                    if save_cyno_loss(conn, killmail, module_id):
                        cyno_count += 1

        mark_archive_processed(
            conn=conn,
            archive_name=archive_path.name,
            json_count=json_count,
            attacker_rows=attacker_rows,
            cyno_count=cyno_count,
        )

        conn.commit()

        print(f"[OK] json={json_count}, attackers={attacker_rows}, cynos={cyno_count}")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {archive_path.name}: {e}")


def print_summary(conn):
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM archive_status")
    archives = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM killmail_attackers")
    attackers = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM cyno_losses")
    cynos = cur.fetchone()[0]

    print("\nDONE")
    print(f"Database: {DB_PATH}")
    print(f"Archives processed: {archives}")
    print(f"Attacker rows: {attackers}")
    print(f"Unique cyno pilots: {cynos}")


def main():
    if not KILLMAILS_DIR.exists():
        print(f"[ERROR] Folder not found: {KILLMAILS_DIR}")
        return

    archives = sorted(KILLMAILS_DIR.glob("killmails-*.tar.bz2"))

    if not archives:
        print(f"[ERROR] No killmail archives found in: {KILLMAILS_DIR}")
        return

    print(f"Found archives: {len(archives)}")
    print(f"DB path: {DB_PATH}")

    conn = init_db()

    for archive_path in archives:
        process_archive(conn, archive_path)

    print_summary(conn)
    conn.close()


if __name__ == "__main__":
    main()