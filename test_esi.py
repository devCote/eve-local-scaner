from esi_client import get_character_id

name = input("Pilot name: ")

character_id = get_character_id(name)

print("Character ID:", character_id)
