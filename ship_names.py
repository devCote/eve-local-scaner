import json
from pathlib import Path

from paths import app_path


SHIP_NAMES_PATH = app_path("ships.json")

_ship_names_cache = None


def load_ship_names():
    global _ship_names_cache

    if _ship_names_cache is not None:
        return _ship_names_cache

    path = Path(SHIP_NAMES_PATH)

    if not path.exists():
        print(f"ships.json not found: {path}")
        _ship_names_cache = {}
        return _ship_names_cache

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Поддержка формата:
        # {"29990": "Loki"}
        # или {"29990": {"name": "Loki"}}
        result = {}

        for key, value in data.items():
            try:
                type_id = int(key)
            except Exception:
                continue

            if isinstance(value, str):
                result[type_id] = value
            elif isinstance(value, dict):
                result[type_id] = value.get("name", str(type_id))
            else:
                result[type_id] = str(type_id)

        _ship_names_cache = result
        return _ship_names_cache

    except Exception as e:
        print("Failed to load ships.json:", e)
        _ship_names_cache = {}
        return _ship_names_cache


def get_ship_name(ship_type_id: int) -> str:
    ship_names = load_ship_names()

    try:
        ship_type_id = int(ship_type_id)
    except Exception:
        return "Unknown"

    return ship_names.get(ship_type_id, f"Type {ship_type_id}")