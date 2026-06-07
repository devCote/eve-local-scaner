import json
import requests

from cache import cache
from datetime import datetime, timezone, timedelta

USER_AGENT = "EVE-Local-Scanner"

ZKILL_URL = "https://zkillboard.com/api"
ESI_URL = "https://esi.evetech.net/latest"

TIMEOUT = 8

TTL_STATS = 1800  # 30 минут
TTL_RECENT = 900  # 15 минут
TTL_KILLMAIL = 86400  # 24 часа
TTL_CYNO = 1800  # 30 минут

CYNO_MODULE_IDS = {
    21096,  # Cynosural Field Generator I
    28646,  # Covert Cynosural Field Generator I
}


def get_json_cached(cache_key: str, url: str, ttl_seconds: int):
    cached = cache.get(cache_key, ttl_seconds=ttl_seconds)

    if cached is not None:
        return cached

    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
        )

        response.raise_for_status()
        data = response.json()

        cache.set(cache_key, data)
        return data

    except Exception as e:
        print("Request error:", url, e)
        return None


def get_zkill_url(character_id: int) -> str:
    return f"https://zkillboard.com/character/{character_id}/"


def get_recent_kills(character_id: int, limit: int = 10):
    cache_key = f"zkill:kills:{character_id}:{limit}"
    url = f"{ZKILL_URL}/kills/characterID/{character_id}/"

    data = get_json_cached(cache_key, url, TTL_RECENT)

    if not data:
        return []

    return data[:limit]


def get_recent_losses(character_id: int, limit: int = 50):
    cache_key = f"zkill:losses:{character_id}:{limit}"
    url = f"{ZKILL_URL}/losses/characterID/{character_id}/"

    data = get_json_cached(cache_key, url, TTL_RECENT)

    if not data:
        return []

    return data[:limit]


def get_full_killmail(killmail_id: int, killmail_hash: str):
    cache_key = f"esi:killmail:{killmail_id}:{killmail_hash}"
    url = f"{ESI_URL}/killmails/{killmail_id}/{killmail_hash}/"

    return get_json_cached(cache_key, url, TTL_KILLMAIL)


def get_zkill_stats(character_id: int):
    cache_key = f"zkill:stats:{character_id}"
    url = f"{ZKILL_URL}/stats/characterID/{character_id}/"

    return get_json_cached(cache_key, url, TTL_STATS)


def debug_zkill_stats(character_id: int):
    stats = get_zkill_stats(character_id)

    if not stats:
        print("No stats")
        return

    print(json.dumps(stats, indent=2))


def get_danger_percent(character_id: int) -> int:
    stats = get_zkill_stats(character_id)

    if not stats:
        return 0

    return stats.get("dangerRatio", 0)


def get_gangRatio(character_id: int) -> int:
    stats = get_zkill_stats(character_id)

    if not stats:
        return 0

    return stats.get("gangRatio", 0)


def get_soloRatio(character_id: int) -> int:
    stats = get_zkill_stats(character_id)

    if not stats:
        return 0

    return stats.get("soloRatio", 0)


def get_risk_level(danger: int) -> str:
    if danger >= 60:
        return "RED"
    if danger >= 40:
        return "YELLOW"
    return "GREEN"


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


def has_cyno_history(character_id: int, limit: int = 50, days: int = 28) -> bool:
    cache_key = f"zkill:cyno:{character_id}:{limit}"

    cached = cache.get(cache_key, ttl_seconds=TTL_CYNO)

    if cached is not None:
        return bool(cached)

    losses = get_recent_losses(character_id, limit=limit)

    # zKill losses не содержит killmail_time, поэтому НЕ фильтруем по времени тут
    losses_to_check = losses[:15]

    checked = 0

    for loss in losses_to_check:
        killmail_id = loss.get("killmail_id")
        killmail_hash = loss.get("zkb", {}).get("hash")

        if not killmail_id or not killmail_hash:
            continue

        checked += 1

        full_killmail = get_full_killmail(killmail_id, killmail_hash)

        if not full_killmail:
            continue

        if has_cyno_fit(full_killmail):
            cache.set(cache_key, True)
            return True

    cache.set(cache_key, False)
    return False
