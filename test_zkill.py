import json
import requests


USER_AGENT = "EVE-Local-Scanner-Test"
ZKILL_URL = "https://zkillboard.com/api"


character_id = 2121046369  # сюда можешь поставить любой characterID


def get(url):
    print("\nREQUEST:")
    print(url)

    r = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )

    print("STATUS:", r.status_code)

    if r.status_code != 200:
        print(r.text)
        return None

    return r.json()


# 1. Recent kills
kills = get(f"{ZKILL_URL}/kills/characterID/{character_id}/")

print("\n=== KILLS RESPONSE TYPE ===")
print(type(kills))

print("\n=== FIRST KILL SHORT ===")
if kills:
    print(json.dumps(kills[0], indent=2))


# 2. Recent losses
losses = get(f"{ZKILL_URL}/losses/characterID/{character_id}/")

print("\n=== LOSSES RESPONSE TYPE ===")
print(type(losses))

print("\n=== FIRST LOSS SHORT ===")
if losses:
    print(json.dumps(losses[0], indent=2))


# 3. Stats
stats = get(f"{ZKILL_URL}/stats/characterID/{character_id}/")

print("\n=== STATS KEYS ===")
if stats:
    print(stats.keys())

print("\n=== STATS SHORT ===")
if stats:
    short = {
        "dangerRatio": stats.get("dangerRatio"),
        "gangRatio": stats.get("gangRatio"),
        "soloRatio": stats.get("soloRatio"),
        "topAllTime": stats.get("topAllTime", [])[:2],
    }

    print(json.dumps(short, indent=2))

print("\n=== TOP ALL TIME CHARACTER ===")
for block in stats.get("topAllTime", []):
    if block.get("type") == "character":
        print(json.dumps(block, indent=2))
