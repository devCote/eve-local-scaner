import requests

ESI_URL = "https://esi.evetech.net/latest"


def get_character_id(character_name: str):
    try:
        response = requests.post(
            f"{ESI_URL}/universe/ids/",
            json=[character_name],
            timeout=10
        )

        if response.status_code != 200:
            return None

        data = response.json()

        characters = data.get("characters", [])

        if not characters:
            return None

        return characters[0]["id"]

    except Exception as e:
        print("ESI ERROR:", e)
        return None

def get_character_info(character_id: int):
    try:
        response = requests.get(
            f"{ESI_URL}/characters/{character_id}/",
            timeout=10
        )

        if response.status_code != 200:
            return None

        return response.json()

    except Exception:
        return None


def get_corporation_info(corp_id: int):
    try:
        response = requests.get(
            f"{ESI_URL}/corporations/{corp_id}/",
            timeout=10
        )

        if response.status_code != 200:
            return None

        return response.json()

    except Exception:
        return None


def get_alliance_info(alliance_id: int):
    try:
        response = requests.get(
            f"{ESI_URL}/alliances/{alliance_id}/",
            timeout=10
        )

        if response.status_code != 200:
            return None

        return response.json()

    except Exception:
        return None


def get_ally_or_corp(character_id: int):
    character = get_character_info(character_id)

    if not character:
        return "?"

    corp_id = character["corporation_id"]
    alliance_id = character.get("alliance_id")

    if alliance_id:
        alliance = get_alliance_info(alliance_id)

        if alliance:
            return alliance.get("ticker", "?")

    corp = get_corporation_info(corp_id)

    if corp:
        return corp.get("ticker", "?")

    return "?"
