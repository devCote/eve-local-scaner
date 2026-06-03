from esi_client import get_character_id
from zkill_client import get_recent_kills, get_zkill_url

name = input("Pilot name: ")

character_id = get_character_id(name)

print("Character ID:", character_id)
print("zKill:", get_zkill_url(character_id))

kills = get_recent_kills(character_id)

print()
print("Recent kills:", len(kills))

for kill in kills[:5]:
    print(
        "Kill ID:",
        kill.get("killmail_id")
    )
