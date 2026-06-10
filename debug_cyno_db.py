import sys
from pathlib import Path

from local_intel_db import (
    get_db_path,
    print_local_db_health,
    get_cyno_info,
    get_recent_cyno_rows,
)

try:
    from esi_client import get_character_id
except Exception:
    get_character_id = None


def resolve_arg(arg: str) -> int | None:
    arg = arg.strip()
    if arg.isdigit():
        return int(arg)
    if get_character_id:
        return get_character_id(arg)
    return None


def main():
    print_local_db_health()
    print()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_cyno_db.py 2122864936")
        print('  python debug_cyno_db.py "Pilot Name"')
        print("\nRecent cyno rows:")
        for row in get_recent_cyno_rows(10):
            print(row)
        return

    character_id = resolve_arg(" ".join(sys.argv[1:]))
    print("character_id:", character_id)

    if not character_id:
        print("Pilot not found / cannot resolve name")
        return

    info_40 = get_cyno_info(character_id, days=40)
    info_all = get_cyno_info(character_id, days=0)

    print("cyno in last 40 days:", info_40)
    print("cyno all time in DB:", info_all)

    if info_40:
        print("zkill:", f"https://zkillboard.com/kill/{info_40['killmail_id']}/")


if __name__ == "__main__":
    main()
