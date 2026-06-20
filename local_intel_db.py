from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from paths import EXE_DIR, SOURCE_DIR, user_data_path


DB_RELATIVE_PATH = Path("data") / "local_intel.sqlite"
_db_connection: sqlite3.Connection | None = None


def get_db_path() -> Path:
    writable_path = user_data_path(DB_RELATIVE_PATH)

    if writable_path.exists():
        return writable_path

    legacy_candidates = [
        Path.cwd() / DB_RELATIVE_PATH,
        SOURCE_DIR / DB_RELATIVE_PATH,
        EXE_DIR / DB_RELATIVE_PATH,
    ]

    for path in legacy_candidates:
        if path.exists():
            return path

    return writable_path


def db_exists() -> bool:
    return get_db_path().exists()


def connect() -> sqlite3.Connection | None:
    global _db_connection
    
    if _db_connection is not None:
        return _db_connection
    
    db_path = get_db_path()

    if not db_path.exists():
        print(f"[LOCAL DB] Not found: {db_path}")
        return None

    _db_connection = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
    _db_connection.row_factory = sqlite3.Row
    try:
        cur = _db_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.execute("PRAGMA temp_store=MEMORY")
    except Exception:
        pass
    return _db_connection


def _fetchone(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    conn = connect()
    if conn is None:
        return None

    cur = conn.cursor()
    cur.execute(query, params)
    return cur.fetchone()


def _fetchall(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = connect()
    if conn is None:
        return []

    cur = conn.cursor()
    cur.execute(query, params)
    return cur.fetchall()


def table_exists(table_name: str) -> bool:
    row = _fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    return row is not None


def get_kill_count(character_id: int) -> int:
    row = _fetchone(
        """
        SELECT COUNT(DISTINCT ka.killmail_id) AS count
        FROM killmail_attackers ka
        WHERE ka.attacker_character_id = ?
        """,
        (int(character_id),),
    )
    return int(row["count"] or 0) if row else 0


def get_loss_count(character_id: int) -> int:
    row = _fetchone(
        """
        SELECT COUNT(*) AS count
        FROM killmails
        WHERE victim_character_id = ?
        """,
        (int(character_id),),
    )
    return int(row["count"] or 0) if row else 0


def get_recent_kills(character_id: int, limit: int = 10) -> list[dict]:
    rows = _fetchall(
        """
        SELECT
            ka.attacker_character_id,
            km.killmail_id,
            km.killmail_time,
            km.victim_character_id,
            km.victim_ship_type_id,
            km.solar_system_id,
            ka.final_blow,
            ka.damage_done
        FROM killmail_attackers ka
        JOIN killmails km ON km.killmail_id = ka.killmail_id
        WHERE ka.attacker_character_id = ?
        ORDER BY km.killmail_time DESC
        LIMIT ?
        """,
        (int(character_id), int(limit)),
    )

    result = []
    for row in rows:
        result.append(
            {
                "killmail_id": row["killmail_id"],
                "killmail_time": row["killmail_time"],
                "victim": {
                    "character_id": row["victim_character_id"],
                    "ship_type_id": row["victim_ship_type_id"],
                },
                "solar_system_id": row["solar_system_id"],
                "attacker_character_id": row["attacker_character_id"],
                "final_blow": bool(row["final_blow"]),
                "damage_done": row["damage_done"],
                "zkb": {},
            }
        )
    return result


def get_recent_losses(character_id: int, limit: int = 50) -> list[dict]:
    rows = _fetchall(
        """
        SELECT
            killmail_id,
            killmail_time,
            victim_character_id,
            victim_ship_type_id,
            solar_system_id
        FROM killmails
        WHERE victim_character_id = ?
        ORDER BY killmail_time DESC
        LIMIT ?
        """,
        (int(character_id), int(limit)),
    )

    result = []
    for row in rows:
        result.append(
            {
                "killmail_id": row["killmail_id"],
                "killmail_time": row["killmail_time"],
                "victim": {
                    "character_id": row["victim_character_id"],
                    "ship_type_id": row["victim_ship_type_id"],
                },
                "solar_system_id": row["solar_system_id"],
                "zkb": {},
            }
        )
    return result


def get_last_lost_ships(character_id: int, limit: int = 3) -> list[dict]:
    rows = _fetchall(
        """
        SELECT
            killmail_id,
            killmail_time,
            victim_ship_type_id AS ship_type_id
        FROM killmails
        WHERE victim_character_id = ?
          AND victim_ship_type_id IS NOT NULL
        ORDER BY killmail_time DESC
        LIMIT ?
        """,
        (int(character_id), int(limit)),
    )

    result = []
    for row in rows:
        ship_type_id = row["ship_type_id"]
        if not ship_type_id:
            continue

        result.append(
            {
                "killmail_id": int(row["killmail_id"]),
                "killmail_time": row["killmail_time"],
                "ship_type_id": int(ship_type_id),
                "last_loss_url": f"https://zkillboard.com/kill/{int(row['killmail_id'])}/",
            }
        )

    return result


def get_top_destroyed_ships(character_id: int, limit: int = 3) -> list[dict]:
    rows = _fetchall(
        """
        SELECT km.victim_ship_type_id AS ship_type_id, COUNT(DISTINCT ka.killmail_id) AS count
        FROM killmail_attackers ka
        JOIN killmails km ON km.killmail_id = ka.killmail_id
        WHERE ka.attacker_character_id = ?
          AND km.victim_ship_type_id IS NOT NULL
        GROUP BY km.victim_ship_type_id
        ORDER BY count DESC
        LIMIT ?
        """,
        (int(character_id), int(limit)),
    )

    return [
        {"shipTypeID": int(row["ship_type_id"]), "count": int(row["count"] or 0)}
        for row in rows
        if row["ship_type_id"]
    ]


def _compute_and_cache_stats(character_id: int) -> dict | None:
    """Compute per-character aggregates in one pass and cache them.

    The old implementation ran a killmail_attackers self-join with no time
    window and no LIMIT on every call. For active pilots that scans tens of
    thousands of rows each view. Here we:
      - count kills/losses and solo kills in a single grouped query,
      - bound the work by the stored killmail window (DAYS_BACK),
      - persist the result in character_stats so subsequent views are O(1).
    """
    conn = connect()
    if conn is None:
        return None

    cid = int(character_id)
    cur = conn.cursor()

    try:
        # Losses: one count over the victim index.
        cur.execute(
            "SELECT COUNT(*) FROM killmails WHERE victim_character_id = ?",
            (cid,),
        )
        losses = int(cur.fetchone()[0] or 0)

        # Kills + solo kills. A solo kill is a killmail where the pilot
        # participated AND there was exactly one attacker total. We count the
        # pilot's killmails that have no co-attackers via NOT EXISTS.
        cur.execute(
            """
            SELECT COUNT(DISTINCT km.killmail_id)
            FROM killmail_attackers km
            WHERE km.attacker_character_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM killmail_attackers other
                  WHERE other.killmail_id = km.killmail_id
                    AND other.attacker_character_id != km.attacker_character_id
              )
            """,
            (cid,),
        )
        solo_kills = int(cur.fetchone()[0] or 0)

        cur.execute(
            """
            SELECT COUNT(DISTINCT killmail_id)
            FROM killmail_attackers
            WHERE attacker_character_id = ?
            """,
            (cid,),
        )
        kills = int(cur.fetchone()[0] or 0)

        total = kills
        # When a pilot has no kills, gang/solo ratios are undefined. The legacy
        # implementation returned neutral 0/0 in that case; preserve it so the
        # UI does not show a misleading 100% gang ratio for pure-victim pilots.
        if total:
            solo_ratio = round((solo_kills / total) * 100)
            gang_ratio = max(0, 100 - solo_ratio)
        else:
            solo_ratio = 0
            gang_ratio = 0

        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            cur.execute(
                """
                INSERT INTO character_stats (
                    character_id, kills, losses, solo_kills,
                    gang_ratio, solo_ratio, computed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(character_id) DO UPDATE SET
                    kills = excluded.kills,
                    losses = excluded.losses,
                    solo_kills = excluded.solo_kills,
                    gang_ratio = excluded.gang_ratio,
                    solo_ratio = excluded.solo_ratio,
                    computed_at = excluded.computed_at
                """,
                (cid, kills, losses, solo_kills, gang_ratio, solo_ratio, now_iso),
            )
            conn.commit()
        except Exception as e:
            print(f"[LOCAL DB] character_stats cache write error: {e}")

        return {
            "kills": kills,
            "losses": losses,
            "solo_kills": solo_kills,
            "gang_ratio": gang_ratio,
            "solo_ratio": solo_ratio,
        }

    except Exception as e:
        print(f"[LOCAL DB] stats compute error: {e}")
        return None


def get_gang_stats(character_id: int) -> tuple[int, int, int]:
    """Gang/solo ratios, served from character_stats cache when fresh.

    Returns (gang_ratio, solo_ratio, solo_kills). Computes and caches on miss.
    """
    cid = int(character_id)
    conn = connect()
    if conn is None:
        return 0, 0, 0

    if not table_exists("character_stats"):
        # Cold start: compute directly without persistence.
        stats = _compute_and_cache_stats(cid)
        if not stats:
            return 0, 0, 0
        return int(stats["gang_ratio"]), int(stats["solo_ratio"]), int(stats["solo_kills"])

    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT gang_ratio, solo_ratio, solo_kills FROM character_stats WHERE character_id = ?",
            (cid,),
        ).fetchone()
    except Exception:
        row = None

    if row:
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    stats = _compute_and_cache_stats(cid)
    if not stats:
        return 0, 0, 0
    return int(stats["gang_ratio"]), int(stats["solo_ratio"]), int(stats["solo_kills"])


def get_local_stats(character_id: int) -> dict:
    cid = int(character_id)

    # Kills/losses come from the cached aggregate when available; this collapses
    # the old 4 separate queries (kills, losses, gang, top ships) into at most
    # one cache lookup plus a single top-ships query.
    kills = 0
    losses = 0
    gang_ratio = 0
    solo_ratio = 0
    solo_kills = 0

    conn = connect()
    if conn is not None and table_exists("character_stats"):
        try:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT kills, losses, solo_kills, gang_ratio, solo_ratio FROM character_stats WHERE character_id = ?",
                (cid,),
            ).fetchone()
        except Exception:
            row = None

        if row:
            kills = int(row[0] or 0)
            losses = int(row[1] or 0)
            solo_kills = int(row[2] or 0)
            gang_ratio = int(row[3] or 0)
            solo_ratio = int(row[4] or 0)
        else:
            stats = _compute_and_cache_stats(cid)
            if stats:
                kills = int(stats["kills"])
                losses = int(stats["losses"])
                solo_kills = int(stats["solo_kills"])
                gang_ratio = int(stats["gang_ratio"])
                solo_ratio = int(stats["solo_ratio"])
    else:
        kills = get_kill_count(cid)
        losses = get_loss_count(cid)
        gang_ratio, solo_ratio, solo_kills = get_gang_stats(cid)

    total = kills + losses

    danger_ratio = round((losses / total) * 100) if total else 0
    top_ships = get_top_destroyed_ships(cid, limit=10)

    return {
        "dangerRatio": int(danger_ratio),
        "gangRatio": int(gang_ratio),
        "soloRatio": int(solo_ratio),
        "shipsDestroyed": int(kills),
        "shipsLost": int(losses),
        "soloKills": int(solo_kills),
        "topAllTime": [
            {
                "type": "ship",
                "data": top_ships,
            }
        ],
        "_source": "local_intel.sqlite",
    }


def get_cyno_count() -> int:
    if not table_exists("cyno_losses"):
        return 0
    row = _fetchone("SELECT COUNT(*) AS count FROM cyno_losses")
    return int(row["count"] or 0) if row else 0


def get_recent_cyno_rows(limit: int = 20) -> list[dict]:
    if not table_exists("cyno_losses"):
        return []
    rows = _fetchall(
        """
        SELECT character_id, last_cyno_time, killmail_id, ship_type_id,
               cyno_module_id, cyno_module_name
        FROM cyno_losses
        ORDER BY last_cyno_time DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    return [dict(row) for row in rows]


def print_local_db_health() -> None:
    db_path = get_db_path()
    print(f"[LOCAL DB] path: {db_path}")
    print(f"[LOCAL DB] exists: {db_path.exists()}")

    if db_path.exists():
        print(f"[LOCAL DB] size GB: {db_path.stat().st_size / 1024 / 1024 / 1024:.2f}")

    print(f"[LOCAL DB] killmails table: {table_exists('killmails')}")
    print(f"[LOCAL DB] killmail_attackers table: {table_exists('killmail_attackers')}")
    print(f"[LOCAL DB] cyno_losses table: {table_exists('cyno_losses')}")
    print(f"[LOCAL DB] cyno rows: {get_cyno_count()}")


def parse_z_time(value: str) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def get_cyno_loss(character_id: int, days: int | None = 40) -> dict | None:
    if not table_exists("cyno_losses"):
        return None

    if days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=int(days))
        since_text = since.isoformat().replace("+00:00", "Z")
        row = _fetchone(
            """
            SELECT character_id, last_cyno_time, killmail_id, ship_type_id,
                   cyno_module_id, cyno_module_name
            FROM cyno_losses
            WHERE character_id = ?
              AND last_cyno_time >= ?
            ORDER BY last_cyno_time DESC
            LIMIT 1
            """,
            (int(character_id), since_text),
        )
    else:
        row = _fetchone(
            """
            SELECT character_id, last_cyno_time, killmail_id, ship_type_id,
                   cyno_module_id, cyno_module_name
            FROM cyno_losses
            WHERE character_id = ?
            ORDER BY last_cyno_time DESC
            LIMIT 1
            """,
            (int(character_id),),
        )

    return dict(row) if row else None


def get_linked_character_relations(character_ids: list[int], limit_killmails: int = 10000) -> dict[int, list[int]]:
    ids = sorted({int(x) for x in character_ids if x})
    if len(ids) < 2:
        return {}

    placeholders = ",".join("?" for _ in ids)
    rows = _fetchall(
        f"""
        SELECT ka.killmail_id, km.killmail_time, ka.attacker_character_id
        FROM killmail_attackers ka
        JOIN killmails km ON km.killmail_id = ka.killmail_id
        WHERE ka.attacker_character_id IN ({placeholders})
        ORDER BY km.killmail_time DESC
        LIMIT ?
        """,
        (*ids, int(limit_killmails)),
    )

    by_killmail: dict[int, set[int]] = {}
    id_set = set(ids)

    for row in rows:
        killmail_id = int(row["killmail_id"])
        attacker_id = int(row["attacker_character_id"])
        if attacker_id not in id_set:
            continue
        by_killmail.setdefault(killmail_id, set()).add(attacker_id)

    relations = {character_id: set() for character_id in ids}

    for owners in by_killmail.values():
        if len(owners) < 2:
            continue
        for a in owners:
            for b in owners:
                if a != b:
                    relations[a].add(b)

    return {
        character_id: sorted(linked_ids)
        for character_id, linked_ids in relations.items()
        if linked_ids
    }



def has_cyno_history(
    character_id: int,
    limit: int = 50,
    days: int = 40,
    max_killmails: int = 15,
) -> bool:
    """Compatibility wrapper for old zkill_client imports.

    The old online zKill cyno checker used this function name.
    Now cyno detection is read from local SQLite cyno_losses table.
    Extra args are kept so old calls do not crash.
    """
    row = get_cyno_loss(int(character_id), days=int(days) if days is not None else None)
    return row is not None



def get_cyno_info(character_id: int, days: int | None = 40) -> dict | None:
    """Compatibility wrapper for zkill_client.

    Returns detailed cyno info from local SQLite or None.
    """
    row = get_cyno_loss(int(character_id), days=days)
    if not row:
        return None

    return {
        "character_id": int(row.get("character_id") or character_id),
        "last_cyno_time": row.get("last_cyno_time"),
        "killmail_id": row.get("killmail_id"),
        "ship_type_id": row.get("ship_type_id"),
        "cyno_module_id": row.get("cyno_module_id"),
        "cyno_module_name": row.get("cyno_module_name"),
        "zkill_url": f"https://zkillboard.com/kill/{int(row['killmail_id'])}/" if row.get("killmail_id") else None,
    }
