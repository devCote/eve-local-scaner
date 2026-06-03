from esi_client import get_character_id
from zkill_client import (
    get_zkill_stats,
    get_danger_percent,
    get_gangRatio,
    get_risk_level,
    get_soloRatio
)

name = input("Pilot name: ")

character_id = get_character_id(name)

if not character_id:
    print("Pilot not found")
    exit()

danger = get_danger_percent(character_id)
gang = get_gangRatio(character_id)
solo = get_soloRatio(character_id)

print()
print("=" * 40)
print("Pilot:", name)
print("Character ID:", character_id)
print("=" * 40)
print("Danger Ratio:", danger)
print("Gang Ratio:", gang)
print("Solo Ratio:", solo)
print("Risk Level:", get_risk_level(danger))
print("=" * 40)
