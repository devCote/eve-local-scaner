from esi_client import get_character_id
from zkill_client import get_recent_losses

name = input("Pilot name: ")
character_id = get_character_id(name)

losses = get_recent_losses(character_id, limit=3)

for loss in losses:
    print("Killmail:", loss.get("killmail_id"))
    victim = loss.get("victim", {})
    items = victim.get("items", [])

    print("Has victim:", bool(victim))
    print("Items count:", len(items))
    print("First items:", items[:5])
    print("-" * 40)
