from esi_client import get_character_id
from zkill_client import debug_zkill_stats

name = input("Pilot name: ")

character_id = get_character_id(name)

print("Character ID:", character_id)

debug_zkill_stats(character_id)
