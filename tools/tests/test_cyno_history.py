# Allow running this script from tools/ while importing runtime modules from project root.
from pathlib import Path as _Path
import sys as _sys
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import json

from esi_client import get_character_id
from zkill_client import (
    get_recent_losses,
    get_full_killmail,
    has_cyno_fit,
    has_cyno_history,
)


name = input("Pilot name: ")

character_id = get_character_id(name)

if not character_id:
    print("Pilot not found")
    exit()

print("Character ID:", character_id)
print("=" * 60)

losses = get_recent_losses(character_id, limit=50)

print("Total losses loaded:", len(losses))
print("=" * 60)

if not losses:
    print("No losses returned from zKill")
    exit()

print("First raw loss object:")
print(json.dumps(losses[0], indent=2))
print("=" * 60)

# ВАЖНО:
# Пока НЕ фильтруем по времени, потому что zKill losses
# может не отдавать killmail_time.
losses_to_check = losses[:15]

print("Losses selected for full check:", len(losses_to_check))
print("=" * 60)

for index, loss in enumerate(losses_to_check, start=1):
    killmail_id = loss.get("killmail_id")
    killmail_hash = loss.get("zkb", {}).get("hash")

    print(f"[{index}] Killmail ID:", killmail_id)
    print("Hash exists:", bool(killmail_hash))

    if not killmail_id or not killmail_hash:
        print("SKIP: missing killmail_id or hash")
        print("-" * 60)
        continue

    full = get_full_killmail(killmail_id, killmail_hash)

    if not full:
        print("SKIP: full killmail not loaded")
        print("-" * 60)
        continue

    victim = full.get("victim", {})
    items = victim.get("items", [])

    print("Victim character:", victim.get("character_id"))
    print("Victim ship:", victim.get("ship_type_id"))
    print("Items count:", len(items))

    print("First 15 item IDs:")
    for item in items[:15]:
        print("-", item.get("item_type_id"))

    found = has_cyno_fit(full)

    print("Cyno found in this killmail:", found)

    if found:
        print("=" * 60)
        print("RESULT: CYNO FOUND")
        print("Found after killmail number:", index)
        print("=" * 60)
        break

    print("-" * 60)

print()
print("Final has_cyno_history():", has_cyno_history(character_id, limit=50, days=28))
