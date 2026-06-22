"""Hybrid zKill-compatible data access.

Current source policy:
- Danger/Gang/Solo/Top Ships are read from zKillboard all-time stats API.
- Cyno check and recent kill/loss lists are read from local data/local_intel.sqlite.

This keeps the Danger column identical to zKillboard all-time dangerRatio.
"""

import json
from datetime import datetime, timezone, timedelta

from cache import cache
from app_http_client import get_json
from local_intel_db import (
    get_recent_kills as get_local_recent_kills,
    get_recent_losses as get_local_recent_losses,
    has_cyno_history as local_has_cyno_history,
    get_cyno_info,
    print_local_db_health,
)

USER_AGENT = "EVE-Local-Intel-Scanner/2.0.0 (+https://github.com/devCote/eve-local-scaner)"
ZKILL_URL = "https://zkillboard.com/api"
ESI_URL = "https://esi.evetech.net/latest"
TIMEOUT = 8

TTL_STATS = 1800      # 30 minutes: zKill stats cache
CYNO_LOOKBACK_DAYS = 40

CYNO_MODULE_IDS = {
    21096,  # Cynosural Field Generator I
    28646,  # Covert Cynosural Field Generator I
    52694,  # Industrial Cynosural Field Generator
}


def get_json_cached(cache_key: str, url: str, ttl_seconds: int):
    """Cached network JSON request. Used for zKill stats only."""
    cached = cache.get(cache_key, ttl_seconds=ttl_seconds)
    if cached is not None:
        return cached

    try:
        data = get_json(url, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
        cache.set(cache_key, data)
        return data
    except Exception as e:
        print("Request error:", url, e)
        return None


def get_zkill_url(character_id: int) -> str:
    return f"https://zkillboard.com/character/{character_id}/"


def get_recent_kills(character_id: int, limit: int = 10):
    """Recent kills from local SQLite, not zKill API.

    Reads directly from SQLite. The DB is indexed (idx_attackers_character_killmail
    + idx_killmails_time) so a repeated query is faster than parsing it back out
    of a JSON cache blob.
    """
    return get_local_recent_kills(character_id, limit=limit)


def get_recent_losses(character_id: int, limit: int = 50):
    """Recent losses from local SQLite, not zKill API."""
    return get_local_recent_losses(character_id, limit=limit)


def get_full_killmail(killmail_id: int, killmail_hash: str | None = None):
    # Full raw killmail JSON is not stored in local_intel.sqlite.
    # Current cyno check uses cyno_losses table, so this is not needed.
    return None


def get_zkill_stats(character_id: int):
    """All-time zKillboard stats.

    Danger must match zKillboard, so this intentionally does not use local
    character_stats. The local DB is still used for recent rows/cyno/popup data.
    """
    cache_key = f"zkill:stats:{character_id}"
    url = f"{ZKILL_URL}/stats/characterID/{character_id}/"

    stats = get_json_cached(cache_key, url, TTL_STATS)
    if not stats:
        return {
            "dangerRatio": 0,
            "gangRatio": 0,
            "soloRatio": 0,
            "topAllTime": [],
            "_source": "zkillboard stats unavailable",
        }

    if isinstance(stats, dict):
        stats["_source"] = "zkillboard all-time stats api"

    return stats


def debug_zkill_stats(character_id: int):
    stats = get_zkill_stats(character_id)
    print(json.dumps(stats, indent=2))


def get_danger_percent(character_id: int) -> int:
    stats = get_zkill_stats(character_id)
    return int(stats.get("dangerRatio", 0)) if stats else 0


def get_gangRatio(character_id: int) -> int:
    stats = get_zkill_stats(character_id)
    return int(stats.get("gangRatio", 0)) if stats else 0


def get_soloRatio(character_id: int) -> int:
    stats = get_zkill_stats(character_id)
    return int(stats.get("soloRatio", 0)) if stats else 0


def get_risk_level(danger: int) -> str:
    if danger >= 60:
        return "RED"
    if danger >= 40:
        return "YELLOW"
    return "GREEN"


# Kept for compatibility with older test/debug scripts.
def has_cyno_in_items(items) -> bool:
    for item in items:
        item_id = item.get("item_type_id")
        if item_id in CYNO_MODULE_IDS:
            return True
        nested_items = item.get("items", [])
        if nested_items and has_cyno_in_items(nested_items):
            return True
    return False


def has_cyno_fit(killmail_data) -> bool:
    victim = killmail_data.get("victim", {})
    items = victim.get("items", [])
    return has_cyno_in_items(items)


def is_recent_killmail(loss, days: int = 28) -> bool:
    kill_time = loss.get("killmail_time")
    if not kill_time:
        return False
    try:
        kill_dt = datetime.fromisoformat(kill_time.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return kill_dt >= cutoff
    except Exception:
        return False


def has_cyno_history(
    character_id: int,
    limit: int = 20,
    days: int = CYNO_LOOKBACK_DAYS,
    max_killmails: int = 5,
) -> bool:
    """Cyno history from local SQLite cyno_losses table.

    cyno_losses.character_id is the PRIMARY KEY, so this is an O(log n) lookup.
    No need to mirror it in the JSON cache.
    """
    return bool(local_has_cyno_history(character_id, days=days))


def get_local_cyno_info(character_id: int, days: int = CYNO_LOOKBACK_DAYS):
    return get_cyno_info(character_id, days=days)


def debug_local_db():
    print_local_db_health()
