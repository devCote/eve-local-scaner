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
