"""Hybrid zKill-compatible data access.

- Danger/Gang/Solo/Top Ships are read from zKillboard stats API, like before.
- Cyno check and recent kill/loss lists are read from local data/local_intel.sqlite.

This keeps the UI stats identical to old zKill behavior while avoiding heavy zKill/ESI
requests for cyno scanning.
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

USER_AGENT = "EVE-Local-Scanner"
ZKILL_URL = "https://zkillboard.com/api"
ESI_URL = "https://esi.evetech.net/latest"
TIMEOUT = 8

TTL_STATS = 1800      # 30 minutes: zKill stats cache
TTL_RECENT = 900      # 15 minutes: local recent rows cache
TTL_CYNO = 1800       # 30 minutes: local cyno cache
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
    """Recent kills from local SQLite, not zKill API."""
    cache_key = f"local:kills:{character_id}:{limit}"
    cached = cache.get(cache_key, ttl_seconds=TTL_RECENT)
    if cached is not None:
        return cached

    data = get_local_recent_kills(character_id, limit=limit)
    cache.set(cache_key, data)
    return data


def get_recent_losses(character_id: int, limit: int = 50):
    """Recent losses from local SQLite, not zKill API."""
    cache_key = f"local:losses:{character_id}:{limit}"
    cached = cache.get(cache_key, ttl_seconds=TTL_RECENT)
    if cached is not None:
        return cached

    data = get_local_recent_losses(character_id, limit=limit)
    cache.set(cache_key, data)
    return data


def get_full_killmail(killmail_id: int, killmail_hash: str | None = None):
    # Full raw killmail JSON is not stored in local_intel.sqlite.
    # Current cyno check uses cyno_losses table, so this is not needed.
    return None


def get_zkill_stats(character_id: int):
    """Stats from zKillboard API, like the old app behavior.

    This restores dangerRatio / gangRatio / soloRatio / topAllTime to zKill values.
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
            "_source": "zkill stats unavailable",
        }

    if isinstance(stats, dict):
        stats["_source"] = "zkillboard stats api"

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
    """Cyno history from local SQLite cyno_losses table."""
    cache_key = f"local:cyno:v4:{character_id}:{days}"
    cached = cache.get(cache_key, ttl_seconds=TTL_CYNO)
    if cached is not None:
        return bool(cached)

    result = local_has_cyno_history(character_id, days=days)
    cache.set(cache_key, bool(result))
    return bool(result)


def get_local_cyno_info(character_id: int, days: int = CYNO_LOOKBACK_DAYS):
    return get_cyno_info(character_id, days=days)


def debug_local_db():
    print_local_db_health()
