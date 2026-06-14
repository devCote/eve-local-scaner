from cache import cache
from app_http_client import get_json, post_json


ESI_URL = "https://esi.evetech.net/latest"
USER_AGENT = "EVE-Local-Intel-Scanner"
TIMEOUT = 10

TTL_CHARACTER_ID = 7 * 24 * 3600
TTL_CHARACTER_INFO = 6 * 3600
TTL_CORP_ALLIANCE_INFO = 24 * 3600



def get_character_id(character_name: str):
    name = str(character_name or "").strip()

    if not name:
        return None

    cache_key = f"esi:character_id:{name.lower()}"
    cached = cache.get(cache_key, ttl_seconds=TTL_CHARACTER_ID)

    if cached is not None:
        return cached

    try:
        data = post_json(
            f"{ESI_URL}/universe/ids/",
            [name],
            user_agent=USER_AGENT,
            timeout=TIMEOUT,
            retries=1,
        )

        if not isinstance(data, dict):
            return None
        characters = data.get("characters", [])

        if not characters:
            return None

        character_id = int(characters[0]["id"])
        cache.set(cache_key, character_id)
        return character_id

    except Exception as e:
        print("ESI ERROR:", e)
        return None


def get_character_info(character_id: int):
    try:
        character_id = int(character_id)
    except Exception:
        return None

    cache_key = f"esi:character_info:{character_id}"
    cached = cache.get(cache_key, ttl_seconds=TTL_CHARACTER_INFO)

    if cached is not None:
        return cached

    try:
        data = get_json(
            f"{ESI_URL}/characters/{character_id}/",
            user_agent=USER_AGENT,
            timeout=TIMEOUT,
            retries=1,
        )

        if not isinstance(data, dict):
            return None
        cache.set(cache_key, data)
        return data

    except Exception:
        return None


def get_corporation_info(corp_id: int):
    try:
        corp_id = int(corp_id)
    except Exception:
        return None

    cache_key = f"esi:corp_info:{corp_id}"
    cached = cache.get(cache_key, ttl_seconds=TTL_CORP_ALLIANCE_INFO)

    if cached is not None:
        return cached

    try:
        data = get_json(
            f"{ESI_URL}/corporations/{corp_id}/",
            user_agent=USER_AGENT,
            timeout=TIMEOUT,
            retries=1,
        )

        if not isinstance(data, dict):
            return None
        cache.set(cache_key, data)
        return data

    except Exception:
        return None


def get_alliance_info(alliance_id: int):
    try:
        alliance_id = int(alliance_id)
    except Exception:
        return None

    cache_key = f"esi:alliance_info:{alliance_id}"
    cached = cache.get(cache_key, ttl_seconds=TTL_CORP_ALLIANCE_INFO)

    if cached is not None:
        return cached

    try:
        data = get_json(
            f"{ESI_URL}/alliances/{alliance_id}/",
            user_agent=USER_AGENT,
            timeout=TIMEOUT,
            retries=1,
        )

        if not isinstance(data, dict):
            return None
        cache.set(cache_key, data)
        return data

    except Exception:
        return None


def get_ally_or_corp(character_id: int):
    character = get_character_info(character_id)

    if not character:
        return "?"

    corp_id = character.get("corporation_id")
    alliance_id = character.get("alliance_id")

    if alliance_id:
        alliance = get_alliance_info(alliance_id)

        if alliance:
            return alliance.get("ticker", "?")

    if corp_id:
        corp = get_corporation_info(corp_id)

        if corp:
            return corp.get("ticker", "?")

    return "?"
