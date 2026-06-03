import json
import requests


def get_zkill_url(character_id: int) -> str:
    return f"https://zkillboard.com/character/{character_id}/"


def get_recent_kills(character_id: int, limit: int = 10):
    url = f"https://zkillboard.com/api/kills/characterID/{character_id}/"

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "EVE-Local-Scanner"},
            timeout=15
        )

        response.raise_for_status()
        data = response.json()

        return data[:limit]

    except Exception as e:
        print("zKill kills error:", e)
        return []


def debug_zkill_stats(character_id: int):
    url = f"https://zkillboard.com/api/stats/characterID/{character_id}/"

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "EVE-Local-Scanner"},
            timeout=15
        )

        print("Status:", response.status_code)

        data = response.json()
        print(json.dumps(data, indent=2))

    except Exception as e:
        print("zKill stats error:", e)


def get_zkill_stats(character_id: int):
    url = f"https://zkillboard.com/api/stats/characterID/{character_id}/"

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "EVE-Local-Scanner"},
            timeout=15
        )

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print("zKill stats error:", e)
        return None

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
