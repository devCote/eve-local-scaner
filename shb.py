import requests
import json
import time

BASE_URL = "https://esi.evetech.net/latest"

ship_names = {}

print("Loading ship groups...")

category = requests.get(f"{BASE_URL}/universe/categories/6/").json()

groups = category["groups"]

print(f"Found {len(groups)} groups")

for group_id in groups:
    try:
        group = requests.get(f"{BASE_URL}/universe/groups/{group_id}/").json()

        type_ids = group.get("types", [])

        if not type_ids:
            continue

        print(f"Group {group_id}: {group.get('name')} ({len(type_ids)} ships)")

        for i in range(0, len(type_ids), 1000):
            batch = type_ids[i : i + 1000]

            response = requests.post(
                f"{BASE_URL}/universe/names/", json=batch, timeout=30
            )

            if response.status_code != 200:
                print(f"Failed names request group={group_id}")
                continue

            names = response.json()

            for item in names:
                if item.get("category") != "inventory_type":
                    continue

                ship_names[str(item["id"])] = item["name"]

            time.sleep(0.1)

    except Exception as e:
        print("ERROR:", group_id, e)

with open("ships.json", "w", encoding="utf-8") as f:
    json.dump(ship_names, f, ensure_ascii=False, indent=2)

print()
print("Saved:", len(ship_names), "ships")
print("File: ship_names.json")
