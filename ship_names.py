import json

with open("ships.json", encoding="utf-8") as f:
    SHIP_NAMES = json.load(f)


def get_ship_name(ship_type_id):
    return SHIP_NAMES.get(str(ship_type_id), f"Unknown ({ship_type_id})")
