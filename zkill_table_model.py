"""API model for compact zKill viewer. No QtWebEngine/Chromium."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import sqlite3
from cache import cache
from app_http_client import get_bytes, get_json, post_json
from paths import user_data_path
from ship_names import get_ship_name as get_local_ship_name
from zkill_client import ESI_URL, USER_AGENT, get_full_killmail

TTL_ESI = 24 * 60 * 60
TTL_KILLMAIL = 60 * 60
TIMEOUT = 8
AVATAR_CACHE_DIR = user_data_path("avatars")
AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)



def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _cached_json(cache_key: str, url: str, ttl_seconds: int = TTL_ESI):
    cached = cache.get(cache_key, ttl_seconds=ttl_seconds)
    if cached is not None:
        return cached

    try:
        data = get_json(url, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
        cache.set(cache_key, data)
        return data
    except Exception as exc:
        print(f"[ZKILL API] request error: {url} -> {exc}")
        return None


def get_type_name(type_id: int) -> str:
    """Resolve any EVE inventory type: ship, module, deployable, structure, etc."""
    type_id = _safe_int(type_id)
    if not type_id:
        return "Unknown"

    cache_key = f"esi:type-name:{type_id}"
    alt_cache_key = f"esi:type_name:{type_id}"

    for key in (cache_key, alt_cache_key):
        cached = cache.get(key, ttl_seconds=TTL_ESI)
        if cached is not None:
            cached_text = str(cached).strip()
            # Old cache could contain fallback "Type 33475". Retry those once
            # because structures/deployables need the direct type endpoint.
            if cached_text and not cached_text.lower().startswith("type "):
                return cached_text

    data = _cached_json(cache_key + ":json", f"{ESI_URL}/universe/types/{type_id}/")
    name = str((data or {}).get("name") or "").strip()

    if not name:
        name = f"Type {type_id}"

    cache.set(cache_key, name)
    cache.set(alt_cache_key, name)
    return name


def shorten_ship_name(name: str) -> str:
    """Shorten common long EVE ship names for compact tables."""
    value = str(name or "").strip()
    if not value:
        return "Unknown"

    replacements = [
        ("Navy Issue", "NI"),
        ("Fleet Issue", "FI"),
        ("Federation Issue", "FI"),
        ("Republic Fleet", "RF"),
        ("Imperial Navy", "IN"),
        ("State Issue", "SI"),
        ("Tribal Issue", "TI"),
    ]
    for old, new in replacements:
        value = value.replace(old, new)

    value = " ".join(value.split())
    return value


def get_ship_name(type_id: int) -> str:
    """Name for the Ship column.

    First use local ships.json for speed. If it returns "Type ####", the victim
    is likely a structure/deployable/non-ship missing from ships.json, so fall
    back to ESI /universe/types/{type_id}/ and show the real type name.
    """
    type_id = _safe_int(type_id)
    if not type_id:
        return "Unknown"

    local_name = shorten_ship_name(get_local_ship_name(type_id))
    if local_name and not local_name.lower().startswith("type "):
        return local_name

    resolved_name = shorten_ship_name(get_type_name(type_id))
    if resolved_name and not resolved_name.lower().startswith("type "):
        return resolved_name

    return local_name or f"Type {type_id}"


def get_character_name(character_id: int) -> str:
    character_id = _safe_int(character_id)
    if not character_id:
        return "Unknown"

    cache_key = f"esi:character-name:{character_id}"
    cached = cache.get(cache_key, ttl_seconds=TTL_ESI)
    if cached is not None:
        return str(cached)

    data = _cached_json(cache_key + ":json", f"{ESI_URL}/characters/{character_id}/")
    name = (data or {}).get("name") or f"#{character_id}"
    cache.set(cache_key, name)
    return name


def get_corporation_name(corporation_id: int) -> str:
    corporation_id = _safe_int(corporation_id)
    if not corporation_id:
        return "Unknown"

    cache_key = f"esi:corp-name:{corporation_id}"
    cached = cache.get(cache_key, ttl_seconds=TTL_ESI)
    if cached is not None:
        return str(cached)

    data = _cached_json(cache_key + ":json", f"{ESI_URL}/corporations/{corporation_id}/")
    name = (data or {}).get("name") or f"Corp #{corporation_id}"
    cache.set(cache_key, name)
    return name


def get_alliance_name(alliance_id: int) -> str:
    alliance_id = _safe_int(alliance_id)
    if not alliance_id:
        return ""

    cache_key = f"esi:alliance-name:{alliance_id}"
    cached = cache.get(cache_key, ttl_seconds=TTL_ESI)
    if cached is not None:
        return str(cached)

    data = _cached_json(cache_key + ":json", f"{ESI_URL}/alliances/{alliance_id}/")
    name = (data or {}).get("name") or f"Alliance #{alliance_id}"
    cache.set(cache_key, name)
    return name


def get_character_profile(character_id: int) -> dict:
    """Compact character info for the zKill header."""
    character_id = _safe_int(character_id)
    if not character_id:
        return {}

    data = _cached_json(f"esi:character-profile:{character_id}", f"{ESI_URL}/characters/{character_id}/") or {}
    if not isinstance(data, dict):
        data = {}

    corp_id = _safe_int(data.get("corporation_id"))
    alliance_id = _safe_int(data.get("alliance_id"))

    names = _bulk_resolve_names({character_id, corp_id, alliance_id})

    birthday = str(data.get("birthday") or "")
    if birthday:
        birthday = birthday.replace("T", " ").replace("Z", "")[:10]

    security_status = data.get("security_status")
    try:
        security_status = f"{float(security_status):.2f}"
    except Exception:
        security_status = "?"

    return {
        "name": names.get(character_id) or data.get("name") or f"#{character_id}",
        "corporation": names.get(corp_id) or (f"Corp #{corp_id}" if corp_id else "Unknown"),
        "alliance": names.get(alliance_id) or ("" if not alliance_id else f"Alliance #{alliance_id}"),
        "security_status": security_status,
        "birthday": birthday or "?",
    }


def get_location_name(solar_system_id: int) -> str:
    solar_system_id = _safe_int(solar_system_id)
    if not solar_system_id:
        return "Unknown"

    cache_key = f"esi:system-name:{solar_system_id}"
    cached = cache.get(cache_key, ttl_seconds=TTL_ESI)
    if cached is not None:
        return str(cached)

    data = _cached_json(cache_key + ":json", f"{ESI_URL}/universe/systems/{solar_system_id}/")
    name = (data or {}).get("name") or f"System #{solar_system_id}"
    cache.set(cache_key, name)
    return name


def get_character_avatar_bytes(character_id: int, size: int = 128) -> bytes:
    """Load character avatar with file cache. Never put bytes into JSON cache."""
    character_id = _safe_int(character_id)
    if not character_id:
        return b""

    size = int(size or 128)
    avatar_path = AVATAR_CACHE_DIR / f"character_{character_id}_{size}.jpg"

    try:
        if avatar_path.exists() and avatar_path.stat().st_size > 0:
            return avatar_path.read_bytes()
    except Exception:
        pass

    try:
        url = f"https://images.evetech.net/characters/{character_id}/portrait?size={size}"
        content = get_bytes(url, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
        if content:
            try:
                avatar_path.write_bytes(content)
            except Exception:
                pass
        return content
    except Exception as exc:
        print(f"[ZKILL API] avatar error: {character_id} -> {exc}")
        return b""


def _extract_hash(recent_item: dict) -> str:
    if not isinstance(recent_item, dict):
        return ""

    direct = recent_item.get("killmail_hash") or recent_item.get("hash")
    if direct:
        return str(direct)

    zkb = recent_item.get("zkb")
    if isinstance(zkb, dict):
        return str(zkb.get("hash") or "")

    return ""


def get_killmail_data(killmail_id: int, killmail_hash: str) -> dict | None:
    killmail_id = _safe_int(killmail_id)
    killmail_hash = str(killmail_hash or "").strip()
    if not killmail_id or not killmail_hash:
        return None

    cache_key = f"esi:killmail-full:{killmail_id}:{killmail_hash}"
    cached = cache.get(cache_key, ttl_seconds=TTL_KILLMAIL)
    if cached is not None:
        return cached

    # First try the existing project function. In the local-DB optimized branch
    # this function intentionally returns None, so we also have a direct fallback.
    data = get_full_killmail(killmail_id, killmail_hash)

    # Fallback to ESI directly.
    if not data:
        data = _cached_json(
            cache_key + ":esi-direct",
            f"{ESI_URL}/killmails/{killmail_id}/{killmail_hash}/",
            ttl_seconds=TTL_KILLMAIL,
        )

    # Fallback to zKillboard killmail endpoint used by the NEW branch.
    if not data:
        data = _cached_json(
            cache_key + ":zkill-direct",
            f"https://zkillboard.com/api/killmail/{killmail_id}/{killmail_hash}/",
            ttl_seconds=TTL_KILLMAIL,
        )

    if data:
        cache.set(cache_key, data)
    return data


def _format_time(raw_time: str) -> str:
    raw_time = str(raw_time or "")
    if not raw_time:
        return ""
    try:
        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        return dt.strftime("%y-%m-%d %H:%M")
    except Exception:
        return raw_time.replace("T", " ").replace("Z", "")[:16]


def _attacker_display(attacker: dict) -> tuple[str, int]:
    if not isinstance(attacker, dict):
        return "Unknown", 0

    character_id = _safe_int(attacker.get("character_id"))
    if character_id:
        return get_character_name(character_id), character_id

    corporation_id = _safe_int(attacker.get("corporation_id"))
    if corporation_id:
        return get_corporation_name(corporation_id), corporation_id

    alliance_id = _safe_int(attacker.get("alliance_id"))
    if alliance_id:
        return get_alliance_name(alliance_id), alliance_id

    ship_type_id = _safe_int(attacker.get("ship_type_id"))
    if ship_type_id:
        return get_ship_name(ship_type_id), ship_type_id

    return "NPC / Unknown", 0


def _opponent_with_participants(name: str, attacker_count: int) -> str:
    """Display opponent as: Name (solo) or Name (N).

    The count means attackers/participants on that killmail. For one attacker we
    show "solo" because it is more useful than "1" in zKill-style intel.
    """
    clean_name = str(name or "Unknown").strip() or "Unknown"
    count = _safe_int(attacker_count)
    if count <= 0:
        return clean_name
    if count == 1:
        return f"{clean_name} (solo)"
    return f"{clean_name} ({count})"


def parse_killmail_row(killmail: dict, perspective_character_id: int = 0, row_kind: str = "") -> dict | None:
    if not isinstance(killmail, dict):
        return None

    try:
        victim = killmail.get("victim") if isinstance(killmail.get("victim"), dict) else {}
        attackers = killmail.get("attackers") if isinstance(killmail.get("attackers"), list) else []

        killmail_id = _safe_int(killmail.get("killmail_id"))
        ship_type_id = _safe_int(victim.get("ship_type_id"))
        solar_system_id = _safe_int(killmail.get("solar_system_id"))
        victim_character_id = _safe_int(victim.get("character_id"))
        victim_corp_id = _safe_int(victim.get("corporation_id"))

        attacker_count = len([a for a in attackers if isinstance(a, dict)])

        if row_kind == "loss" or (perspective_character_id and victim_character_id == perspective_character_id):
            final_blow = next((a for a in attackers if isinstance(a, dict) and a.get("final_blow")), None)
            if not final_blow and attackers:
                final_blow = attackers[0]
            opponent, opponent_id = _attacker_display(final_blow or {})
        else:
            opponent_id = victim_character_id or victim_corp_id
            if victim_character_id:
                opponent = get_character_name(victim_character_id)
            elif victim_corp_id:
                opponent = get_corporation_name(victim_corp_id)
            else:
                opponent = "Victim / Unknown"

        opponent = _opponent_with_participants(opponent, attacker_count)

        raw_time = str(killmail.get("killmail_time") or "")
        return {
            "kind": "loss" if row_kind == "loss" else "kill",
            "date": _format_time(raw_time),
            "raw_time": raw_time,
            "ship_name": get_ship_name(ship_type_id),
            "ship_type_id": ship_type_id,
            "location": get_location_name(solar_system_id),
            "location_id": solar_system_id,
            "opponent": opponent,
            "opponent_id": opponent_id,
            "killmail_id": killmail_id,
            "url": f"https://zkillboard.com/kill/{killmail_id}/" if killmail_id else "",
        }
    except Exception as exc:
        print(f"[ZKILL API] parse killmail error: {exc}")
        return None



def _bulk_resolve_names(ids: set[int]) -> dict[int, str]:
    """Resolve many EVE IDs with one ESI request instead of 50+ requests.

    Uses JSON cache per ID. This is the main speed fix for compact zKill viewer.
    """
    clean_ids = sorted({_safe_int(value) for value in ids if _safe_int(value) > 0})
    if not clean_ids:
        return {}

    result: dict[int, str] = {}
    missing: list[int] = []

    for eve_id in clean_ids:
        cache_key = f"esi:name:{eve_id}"
        cached = cache.get(cache_key, ttl_seconds=TTL_ESI)
        if cached is not None:
            result[eve_id] = str(cached)
        else:
            missing.append(eve_id)

    # ESI universe/names has request-size limits; keep chunks conservative.
    for idx in range(0, len(missing), 500):
        chunk = missing[idx:idx + 500]
        if not chunk:
            continue

        try:
            data = post_json(
                f"{ESI_URL}/universe/names/",
                chunk,
                user_agent=USER_AGENT,
                timeout=TIMEOUT,
                retries=1,
            )
            for item in data or []:
                if not isinstance(item, dict):
                    continue
                eve_id = _safe_int(item.get("id"))
                name = str(item.get("name") or f"#{eve_id}")
                if eve_id:
                    result[eve_id] = name
                    cache.set(f"esi:name:{eve_id}", name)
        except Exception as exc:
            print(f"[ZKILL API] bulk name resolve error: {exc}")
            for eve_id in chunk:
                result.setdefault(eve_id, f"#{eve_id}")

    return result


def _batch_final_blow_attackers(killmail_ids: list[int]) -> dict[int, int]:
    """Resolve final-blow attackers for many loss killmails in one SQLite query."""
    ids = sorted({_safe_int(value) for value in killmail_ids if _safe_int(value) > 0})
    if not ids:
        return {}

    try:
        from local_intel_db import get_db_path

        db_path = get_db_path()
        if not db_path.exists():
            return {}

        placeholders = ",".join("?" for _ in ids)
        query = f"""
            SELECT killmail_id, attacker_character_id, final_blow, damage_done
            FROM killmail_attackers
            WHERE killmail_id IN ({placeholders})
              AND attacker_character_id IS NOT NULL
            ORDER BY killmail_id, final_blow DESC, damage_done DESC
        """

        result: dict[int, int] = {}
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(query, ids)
            for row in cur.fetchall():
                killmail_id = _safe_int(row["killmail_id"])
                if killmail_id not in result:
                    result[killmail_id] = _safe_int(row["attacker_character_id"])
        return result
    except Exception as exc:
        print(f"[ZKILL API] batch final-blow lookup failed: {exc}")
        return {}


def _batch_attacker_counts(killmail_ids: list[int]) -> dict[int, int]:
    """Count attackers/participants for many killmails using local SQLite."""
    ids = sorted({_safe_int(value) for value in killmail_ids if _safe_int(value) > 0})
    if not ids:
        return {}

    try:
        from local_intel_db import get_db_path

        db_path = get_db_path()
        if not db_path.exists():
            return {}

        placeholders = ",".join("?" for _ in ids)
        query = f"""
            SELECT killmail_id, COUNT(*) AS attacker_count
            FROM killmail_attackers
            WHERE killmail_id IN ({placeholders})
            GROUP BY killmail_id
        """

        result: dict[int, int] = {}
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(query, ids)
            for row in cur.fetchall():
                result[_safe_int(row["killmail_id"])] = _safe_int(row["attacker_count"])
        return result
    except Exception as exc:
        print(f"[ZKILL API] batch attacker count lookup failed: {exc}")
        return {}


def _looks_like_local_summary(item: dict) -> bool:
    """Rows from local_intel_db already contain enough data for ship/location.

    local_intel_db.get_recent_kills/get_recent_losses returns compact rows:
    killmail_id, killmail_time, victim.ship_type_id, solar_system_id.
    They usually do NOT contain zkb.hash, so trying to load a full ESI killmail
    first makes every row fall back to "Full killmail not loaded".
    """
    if not isinstance(item, dict):
        return False
    victim = item.get("victim")
    return bool(
        item.get("killmail_id")
        and item.get("killmail_time")
        and isinstance(victim, dict)
        and (victim.get("ship_type_id") or item.get("victim_ship_type_id"))
        and (item.get("solar_system_id") or item.get("system_id"))
    )


def _get_final_blow_attacker_from_local_db(killmail_id: int) -> int:
    """Find final-blow attacker from compact local SQLite DB.

    This is only used for Loss rows because local loss summaries do not include
    attackers. If anything goes wrong, return 0 and keep the UI working.
    """
    killmail_id = _safe_int(killmail_id)
    if not killmail_id:
        return 0

    try:
        from local_intel_db import get_db_path

        db_path = get_db_path()
        if not db_path.exists():
            return 0

        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                """
                SELECT attacker_character_id
                FROM killmail_attackers
                WHERE killmail_id = ?
                  AND attacker_character_id IS NOT NULL
                ORDER BY final_blow DESC, damage_done DESC
                LIMIT 1
                """,
                (killmail_id,),
            )
            row = cur.fetchone()
            return _safe_int(row["attacker_character_id"]) if row else 0
    except Exception as exc:
        print(f"[ZKILL API] local final-blow lookup failed: {killmail_id} -> {exc}")
        return 0


def parse_summary_row(
    item: dict,
    perspective_character_id: int = 0,
    row_kind: str = "",
    name_map: dict[int, str] | None = None,
    final_blow_map: dict[int, int] | None = None,
    attacker_count_map: dict[int, int] | None = None,
) -> dict | None:
    """Parse compact local DB row without requiring full ESI killmail JSON."""
    if not isinstance(item, dict):
        return None

    name_map = name_map or {}
    final_blow_map = final_blow_map or {}
    attacker_count_map = attacker_count_map or {}

    try:
        victim = item.get("victim") if isinstance(item.get("victim"), dict) else {}
        killmail_id = _safe_int(item.get("killmail_id"))
        raw_time = str(item.get("killmail_time") or "")
        ship_type_id = _safe_int(victim.get("ship_type_id") or item.get("victim_ship_type_id"))
        solar_system_id = _safe_int(item.get("solar_system_id") or item.get("system_id"))
        victim_character_id = _safe_int(victim.get("character_id") or item.get("victim_character_id"))
        victim_corp_id = _safe_int(victim.get("corporation_id") or item.get("victim_corporation_id"))

        kind = "loss" if row_kind == "loss" else "kill"

        if kind == "loss":
            attacker_id = _safe_int(item.get("attacker_character_id")) or final_blow_map.get(killmail_id, 0)
            if attacker_id:
                opponent = name_map.get(attacker_id) or f"#{attacker_id}"
                opponent_id = attacker_id
            else:
                opponent = "NPC"
                opponent_id = 0
        else:
            opponent_id = victim_character_id or victim_corp_id
            if opponent_id:
                opponent = name_map.get(opponent_id) or f"#{opponent_id}"
            else:
                opponent = "Victim / Unknown"

        attacker_count = _safe_int(item.get("attacker_count")) or attacker_count_map.get(killmail_id, 0)
        opponent = _opponent_with_participants(opponent, attacker_count)

        return {
            "kind": kind,
            "date": _format_time(raw_time),
            "raw_time": raw_time,
            "ship_name": get_ship_name(ship_type_id),
            "ship_type_id": ship_type_id,
            "location": name_map.get(solar_system_id) or (f"System #{solar_system_id}" if solar_system_id else "Unknown"),
            "location_id": solar_system_id,
            "opponent": opponent,
            "opponent_id": opponent_id,
            "killmail_id": killmail_id,
            "url": f"https://zkillboard.com/kill/{killmail_id}/" if killmail_id else "",
        }
    except Exception as exc:
        print(f"[ZKILL API] parse summary row error: {exc}")
        return None

def _fallback_row(item: dict, row_kind: str) -> dict:
    killmail_id = _safe_int(item.get("killmail_id")) if isinstance(item, dict) else 0
    raw_time = str((item or {}).get("killmail_time") or "") if isinstance(item, dict) else ""
    zkb = item.get("zkb") if isinstance(item, dict) else None
    if isinstance(zkb, dict) and not raw_time:
        raw_time = str(zkb.get("killTime") or "")
    return {
        "kind": row_kind,
        "date": _format_time(raw_time),
        "raw_time": raw_time,
        "ship_name": "Full killmail not loaded",
        "ship_type_id": 0,
        "location": "Unknown",
        "location_id": 0,
        "opponent": "Unknown",
        "opponent_id": 0,
        "killmail_id": killmail_id,
        "url": f"https://zkillboard.com/kill/{killmail_id}/" if killmail_id else "",
    }


def _format_recent_list(
    character_id: int,
    recent_list: list,
    row_kind: str,
    name_map: dict[int, str] | None = None,
    final_blow_map: dict[int, int] | None = None,
    attacker_count_map: dict[int, int] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    name_map = name_map or {}
    final_blow_map = final_blow_map or {}
    attacker_count_map = attacker_count_map or {}

    for item in recent_list or []:
        if not isinstance(item, dict):
            continue

        # Current optimized zkill_client reads recent kills/losses from local
        # SQLite. Those rows already have ship/system/time, but no zkb.hash.
        # Parse them directly: fast and no full killmail download per row.
        if _looks_like_local_summary(item):
            row = parse_summary_row(
                item,
                perspective_character_id=character_id,
                row_kind=row_kind,
                name_map=name_map,
                final_blow_map=final_blow_map,
                attacker_count_map=attacker_count_map,
            )
            if row:
                rows.append(row)
                continue

        killmail_id = _safe_int(item.get("killmail_id"))
        killmail_hash = _extract_hash(item)
        full = get_killmail_data(killmail_id, killmail_hash)

        if full:
            row = parse_killmail_row(full, perspective_character_id=character_id, row_kind=row_kind)
            if row:
                rows.append(row)
        else:
            rows.append(_fallback_row(item, row_kind))

    rows.sort(key=lambda r: r.get("raw_time") or r.get("date") or "", reverse=True)
    return rows



def format_kills_losses_data_fast_local(character_id: int, kills_list: list, losses_list: list) -> dict:
    """Format local SQLite summaries without any network name resolving.

    This is intentionally less pretty than format_kills_losses_data(), but it is
    the path that makes the zKill tab appear immediately from DB. Names/system
    labels are refreshed later by the normal formatter.
    """
    character_id = _safe_int(character_id)

    killmail_ids: list[int] = []
    loss_killmail_ids: list[int] = []
    for item in kills_list or []:
        if isinstance(item, dict):
            killmail_ids.append(_safe_int(item.get("killmail_id")))
    for item in losses_list or []:
        if isinstance(item, dict):
            killmail_id = _safe_int(item.get("killmail_id"))
            killmail_ids.append(killmail_id)
            loss_killmail_ids.append(killmail_id)

    # SQLite-only lookups, no ESI/API. Keeps instant DB-first rendering fast.
    final_blow_map = _batch_final_blow_attackers(loss_killmail_ids)
    attacker_count_map = _batch_attacker_counts(killmail_ids)

    kills = _format_recent_list(
        character_id,
        kills_list,
        "kill",
        name_map={},
        final_blow_map={},
        attacker_count_map=attacker_count_map,
    )
    losses = _format_recent_list(
        character_id,
        losses_list,
        "loss",
        name_map={},
        final_blow_map=final_blow_map,
        attacker_count_map=attacker_count_map,
    )
    combined = list(kills) + list(losses)
    combined.sort(key=lambda r: r.get("raw_time") or r.get("date") or "", reverse=True)

    return {
        "character_id": character_id,
        "kills": kills,
        "losses": losses,
        "combined": combined,
        "fast_local": True,
    }

def format_kills_losses_data(character_id: int, kills_list: list, losses_list: list) -> dict:
    character_id = _safe_int(character_id)

    # Pre-collect names and final-blow attackers in batches. Without this the
    # compact viewer can do 50-100 sequential ESI/SQLite calls and feel slower
    # than the old browser.
    ids_to_resolve: set[int] = set()
    loss_killmail_ids: list[int] = []
    all_killmail_ids: list[int] = []

    for item in kills_list or []:
        if not isinstance(item, dict):
            continue
        killmail_id = _safe_int(item.get("killmail_id"))
        all_killmail_ids.append(killmail_id)
        victim = item.get("victim") if isinstance(item.get("victim"), dict) else {}
        ids_to_resolve.add(_safe_int(item.get("solar_system_id") or item.get("system_id")))
        ids_to_resolve.add(_safe_int(victim.get("character_id") or item.get("victim_character_id")))
        ids_to_resolve.add(_safe_int(victim.get("corporation_id") or item.get("victim_corporation_id")))

    for item in losses_list or []:
        if not isinstance(item, dict):
            continue
        ids_to_resolve.add(_safe_int(item.get("solar_system_id") or item.get("system_id")))
        killmail_id = _safe_int(item.get("killmail_id"))
        all_killmail_ids.append(killmail_id)
        loss_killmail_ids.append(killmail_id)

    final_blow_map = _batch_final_blow_attackers(loss_killmail_ids)
    attacker_count_map = _batch_attacker_counts(all_killmail_ids)
    ids_to_resolve.update(final_blow_map.values())
    ids_to_resolve.discard(0)

    name_map = _bulk_resolve_names(ids_to_resolve)

    kills = _format_recent_list(
        character_id,
        kills_list,
        "kill",
        name_map=name_map,
        final_blow_map=final_blow_map,
        attacker_count_map=attacker_count_map,
    )
    losses = _format_recent_list(
        character_id,
        losses_list,
        "loss",
        name_map=name_map,
        final_blow_map=final_blow_map,
        attacker_count_map=attacker_count_map,
    )
    combined = list(kills) + list(losses)
    combined.sort(key=lambda r: r.get("raw_time") or r.get("date") or "", reverse=True)

    return {
        "character_id": character_id,
        "kills": kills,
        "losses": losses,
        "combined": combined,
    }
