from concurrent.futures import ThreadPoolExecutor, as_completed

from cache import cache
from app_http_client import get_json, post_json


ESI_URL = "https://esi.evetech.net/latest"
USER_AGENT = "EVE-Local-Intel-Scanner"
TIMEOUT = 10

TTL_CHARACTER_ID = 7 * 24 * 3600
TTL_CHARACTER_INFO = 6 * 3600
TTL_CORP_ALLIANCE_INFO = 24 * 3600

# ESI POST endpoints accept up to 1000 items per request. Keep chunks
# conservative to stay safely under the limit and reduce per-request payload.
ESI_BATCH_CHUNK = 500


def _safe_int(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _ticker_cache_key(eve_id: int) -> str:
    # v2 ignores older cache entries accidentally filled with full names by
    # /universe/names/. That endpoint returns entity names, not corp/alliance
    # tickers.
    return f"esi:ticker:v2:{int(eve_id)}"


def _valid_ticker(value) -> str:
    ticker = str(value or "").strip()
    if not ticker or ticker == "?":
        return ""
    return ticker


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


def resolve_character_ids(names: list[str]) -> dict[str, int]:
    """Resolve many pilot names to character IDs in one ESI request.

    Instead of one POST /universe/ids/ per pilot (50+ requests for a full local),
    ESI accepts up to 1000 names in a single request. Returns name -> id map.

    Cached names are reused; only missing ones hit the network.
    """
    result: dict[str, int] = {}

    # Normalize and de-duplicate while preserving original casing for keys.
    normalized: dict[str, str] = {}
    for raw in names or []:
        name = str(raw or "").strip()
        if name:
            normalized[name] = name.lower()

    if not normalized:
        return result

    missing: list[str] = []

    for name, lowered in normalized.items():
        cache_key = f"esi:character_id:{lowered}"
        cached = cache.get(cache_key, ttl_seconds=TTL_CHARACTER_ID)
        if cached is not None:
            try:
                result[name] = int(cached)
            except Exception:
                missing.append(name)
        else:
            missing.append(name)

    # Cache negative results so we don't repeatedly ask ESI for names it can't
    # resolve within the TTL window.
    unresolved_key = "esi:character_id:_unresolved_set"
    unresolved = cache.get(unresolved_key, ttl_seconds=TTL_CHARACTER_ID)
    try:
        unresolved_set = set(int(x) if str(x).lstrip("-").isdigit() else x for x in (unresolved or []))
    except Exception:
        unresolved_set = set()

    missing = [n for n in missing if n not in unresolved_set]

    for idx in range(0, len(missing), ESI_BATCH_CHUNK):
        chunk = missing[idx:idx + ESI_BATCH_CHUNK]
        if not chunk:
            continue

        try:
            data = post_json(
                f"{ESI_URL}/universe/ids/",
                chunk,
                user_agent=USER_AGENT,
                timeout=TIMEOUT,
                retries=1,
            )

            if not isinstance(data, dict):
                continue

            # Map lowercase name -> id from the response, then match back to
            # the original-cased names we asked for.
            id_by_lower: dict[str, int] = {}
            for entry in data.get("characters", []) or []:
                if not isinstance(entry, dict):
                    continue
                entry_name = str(entry.get("name") or "").strip()
                entry_id = entry.get("id")
                if entry_name and entry_id:
                    try:
                        id_by_lower[entry_name.lower()] = int(entry_id)
                    except Exception:
                        continue

            for name in chunk:
                char_id = id_by_lower.get(name.lower())
                if char_id is not None:
                    result[name] = char_id
                    cache.set(f"esi:character_id:{name.lower()}", char_id)
                else:
                    unresolved_set.add(name)

        except Exception as e:
            print("ESI batch ids error:", e)

    # Persist unresolved names so we skip them next time within the TTL window.
    if unresolved_set:
        cache.set(unresolved_key, list(unresolved_set))

    return result


def resolve_affiliation_tickers(corporation_ids: list[int], alliance_ids: list[int]) -> dict[int, str]:
    """Resolve real corp/alliance tickers.

    Important: POST /universe/names/ returns full entity names, not tickers.
    Tickers are only available from:
      GET /corporations/{corporation_id}/
      GET /alliances/{alliance_id}/

    This function keeps the old public signature, but internally fetches real
    ticker fields and caches them under a v2 key so stale full-name cache entries
    from older builds are ignored.
    """
    result: dict[int, str] = {}

    corp_unique = sorted({_safe_int(x) for x in corporation_ids or [] if _safe_int(x) > 0})
    alliance_unique = sorted({_safe_int(x) for x in alliance_ids or [] if _safe_int(x) > 0})

    tasks: list[tuple[str, int]] = []

    for corp_id in corp_unique:
        cached = cache.get(_ticker_cache_key(corp_id), ttl_seconds=TTL_CORP_ALLIANCE_INFO)
        ticker = _valid_ticker(cached)
        if ticker:
            result[corp_id] = ticker
        else:
            tasks.append(("corp", corp_id))

    for alliance_id in alliance_unique:
        cached = cache.get(_ticker_cache_key(alliance_id), ttl_seconds=TTL_CORP_ALLIANCE_INFO)
        ticker = _valid_ticker(cached)
        if ticker:
            result[alliance_id] = ticker
        else:
            tasks.append(("alliance", alliance_id))

    if not tasks:
        return result

    def fetch_one(kind: str, eve_id: int) -> tuple[int, str]:
        if kind == "alliance":
            info = get_alliance_info(eve_id)
        else:
            info = get_corporation_info(eve_id)

        if not isinstance(info, dict):
            return eve_id, ""

        ticker = _valid_ticker(info.get("ticker"))
        if ticker:
            cache.set(_ticker_cache_key(eve_id), ticker)
        return eve_id, ticker

    # ESI has no batch ticker endpoint. Use a small worker pool so prefetch is
    # still fast without hammering ESI.
    max_workers = min(8, max(1, len(tasks)))
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(fetch_one, kind, eve_id): (kind, eve_id)
                for kind, eve_id in tasks
            }
            for future in as_completed(future_map):
                kind, eve_id = future_map[future]
                try:
                    resolved_id, ticker = future.result()
                    if ticker:
                        result[resolved_id] = ticker
                except Exception as e:
                    print(f"ESI ticker resolve error: {kind} {eve_id}: {e}")
    except Exception as e:
        print("ESI ticker pool error:", e)

    return result


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
    # Fast path: after prefetch_local_pilots() warms the real ticker cache,
    # avoid the full corp/alliance info fetch entirely.
    character = get_character_info(character_id)

    if not character:
        return "?"

    corp_id = character.get("corporation_id")
    alliance_id = character.get("alliance_id")

    if alliance_id:
        cached_ticker = cache.get(_ticker_cache_key(alliance_id), ttl_seconds=TTL_CORP_ALLIANCE_INFO)
        if cached_ticker:
            return str(cached_ticker)

        alliance = get_alliance_info(alliance_id)

        if alliance:
            ticker = alliance.get("ticker", "?")
            if ticker and ticker != "?":
                cache.set(_ticker_cache_key(alliance_id), ticker)
            return ticker

    if corp_id:
        cached_ticker = cache.get(_ticker_cache_key(corp_id), ttl_seconds=TTL_CORP_ALLIANCE_INFO)
        if cached_ticker:
            return str(cached_ticker)

        corp = get_corporation_info(corp_id)

        if corp:
            ticker = corp.get("ticker", "?")
            if ticker and ticker != "?":
                cache.set(_ticker_cache_key(corp_id), ticker)
            return ticker

    return "?"


def prefetch_local_pilots(pilot_names: list[str]) -> dict[str, int]:
    """Resolve all pilot names and warm up corp/alliance ticker cache.

    Called once before PilotWorker threads start, so that the per-pilot workers
    find character_id and ticker already in cache and make almost no network
    requests. Returns name -> character_id for the names that resolved.

    Flow:
      1. One POST /universe/ids/ for all names (chunked).
      2. For each resolved character_id: GET /characters/{id}/ (still per-id,
         ESI has no batch characters endpoint, but these are cached 6h).
      3. Collect unique corp_id + alliance_id and resolve real tickers via
         corporation/alliance info endpoints. Warm the ticker cache so the
         per-pilot get_ally_or_corp() becomes a cache hit.
    """
    name_to_id = resolve_character_ids(pilot_names)
    character_ids = sorted(set(name_to_id.values()))

    if not character_ids:
        return name_to_id

    # Fetch character info (corporation_id / alliance_id) for each resolved
    # pilot. ESI has no batch characters endpoint, but these are cached and
    # cheap once warm. Doing it here front-loads the work so PilotWorker threads
    # don't each block on it.
    corp_ids: set[int] = set()
    alliance_ids: set[int] = set()

    for character_id in character_ids:
        info = get_character_info(character_id) or {}
        corp_id = _safe_int(info.get("corporation_id"))
        alliance_id = _safe_int(info.get("alliance_id"))
        if corp_id:
            corp_ids.add(corp_id)
        if alliance_id:
            alliance_ids.add(alliance_id)

    # Resolve real tickers and warm the ticker cache. After this, each
    # per-pilot get_ally_or_corp() call is a pure cache hit.
    ticker_map = resolve_affiliation_tickers(list(corp_ids), list(alliance_ids))

    # Mirror batch ticker results into the per-id corp/alliance info cache keys
    # used by get_corporation_info / get_alliance_info, so those also become
    # cache hits without re-fetching full corp info.
    for eve_id, ticker in ticker_map.items():
        cache.set(_ticker_cache_key(eve_id), ticker)

    return name_to_id
