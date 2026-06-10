import json
import tarfile
import sys
from pathlib import Path


KILLMAILS_DIR = Path("killmails")

CYNO_MODULES = {
    21096: "Cynosural Field Generator I",
    28646: "Covert Cynosural Field Generator I",
    52694: "Industrial Cynosural Field Generator",
}


def find_cyno_items(items):
    found = []

    for item in items:
        item_type_id = item.get("item_type_id")

        if item_type_id in CYNO_MODULES:
            found.append((item_type_id, CYNO_MODULES[item_type_id]))

        found.extend(find_cyno_items(item.get("items", [])))

    return found


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_scan_archives_for_pilot.py CHARACTER_ID")
        return

    character_id = int(sys.argv[1])

    archives = sorted(KILLMAILS_DIR.glob("killmails-*.tar.bz2"))

    print(f"Scanning archives: {len(archives)}")
    print(f"Character ID: {character_id}")

    losses_found = 0
    cyno_losses_found = 0

    for archive_path in archives:
        with tarfile.open(archive_path, "r:bz2") as tar:
            for member in tar:
                if not member.isfile() or not member.name.endswith(".json"):
                    continue

                f = tar.extractfile(member)
                if not f:
                    continue

                try:
                    km = json.load(f)
                except Exception:
                    continue

                victim = km.get("victim", {})
                if victim.get("character_id") != character_id:
                    continue

                losses_found += 1

                killmail_id = km.get("killmail_id")
                killmail_time = km.get("killmail_time")
                ship_type_id = victim.get("ship_type_id")
                items = victim.get("items", [])

                cynos = find_cyno_items(items)

                print()
                print(f"[LOSS] {killmail_time} kill={killmail_id} ship={ship_type_id}")
                print(f"URL: https://zkillboard.com/kill/{killmail_id}/")

                if cynos:
                    cyno_losses_found += 1
                    print("[CYNO FOUND]")
                    for module_id, module_name in cynos:
                        print(f"  {module_id} - {module_name}")
                else:
                    print("[NO CYNO MODULE IN VICTIM ITEMS]")

    print()
    print("Done.")
    print(f"Losses found: {losses_found}")
    print(f"Cyno losses found: {cyno_losses_found}")


if __name__ == "__main__":
    main()