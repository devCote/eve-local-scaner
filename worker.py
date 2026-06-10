import re
from PySide6.QtCore import QObject, Signal, QRunnable

from ship_names import get_ship_name
from local_intel_db import get_last_lost_ships

from esi_client import (
    get_character_id,
    get_ally_or_corp,
)

from zkill_client import (
    get_zkill_stats,
    has_cyno_history,
)


class PilotWorkerSignals(QObject):
    finished = Signal(int, dict)


class CynoWorkerSignals(QObject):
    finished = Signal(int, bool)


def get_top_ship_ids_from_stats(stats: dict, limit: int = 3) -> list[int]:
    if not stats:
        return []

    top_all_time = stats.get("topAllTime")

    if not isinstance(top_all_time, list):
        return []

    for block in top_all_time:
        if not isinstance(block, dict):
            continue

        if block.get("type") != "ship":
            continue

        ships = block.get("data")

        if not isinstance(ships, list):
            return []

        result = []

        for ship in ships[:limit]:
            if not isinstance(ship, dict):
                continue

            ship_type_id = ship.get("shipTypeID")

            if ship_type_id:
                result.append(ship_type_id)

        return result

    return []


def is_ignored_last_ship_name(name: str) -> bool:
    """Skip non-useful losses in Last Ships.

    Last Ships should show real pilot ships only, not capsules, shuttles,
    rookie ships, structures, deployables, tractor units, drones/fighters,
    containers, wrecks, or unresolved EVERef fallback names like "Type 3".
    """
    raw = str(name or "").strip()
    lowered = raw.lower()

    if not lowered or lowered in {"?", "unknown", "none", "-"}:
        return True

    # EVERef fallback names for unresolved type IDs.
    # Examples: Type 3, Type 4, Type 12345
    if re.fullmatch(r"type\s*\d+", lowered):
        return True

    ignored_exact = {
        "capsule",
        "capsule - genolution auroral 197-variant",

        # rookie starter ships
        "ibis",
        "velator",
        "reaper",
        "impairor",
    }

    if lowered in ignored_exact:
        return True

    ignored_parts = [
        "capsule",
        "shuttle",

        # rookie starter ships
        "ibis",
        "velator",
        "reaper",
        "impairor",

        # structures / citadels / Upwell
        "citadel",
        "engineering complex",
        "refinery",
        "upwell",
        "structure",
        "customs office",
        "player owned customs office",
        "control tower",
        "moon mining",
        "drilling platform",
        "jump bridge",
        "cyno beacon",
        "cynosural beacon",
        "cynosural system jammer",
        "ansiblex",
        "pharolux",
        "tenebrex",
        "astrahus",
        "fortizar",
        "keepstar",
        "raitaru",
        "azbel",
        "sotiyo",
        "athanor",
        "tatara",

        # deployables / tractors / bubbles
        "mobile tractor",
        "tractor unit",
        "mobile depot",
        "mobile cynosural",
        "mobile scan inhibitor",
        "mobile micro jump",
        "mobile observatory",
        "mobile siphon",
        "warp disruption probe",
        "mobile warp disruptor",
        "warp disruptor probe",
        "bubble",
        "deployable",

        # cans / wrecks / drones / misc objects
        "cargo container",
        "secure container",
        "audit log secure container",
        "freight container",
        "wreck",
        "drone",
        "fighter",
        "sentry gun",
        "billboard",
    ]

    return any(part in lowered for part in ignored_parts)


def build_last_lost_ships(character_id: int, limit: int = 3) -> list[dict]:
    """Build UI data for the Last Ships column from local SQLite losses.

    Capsule and Shuttle losses are skipped, so the column shows real ships.
    """
    # Fetch more than 3 because the latest losses may be Capsule/Shuttle.
    losses = get_last_lost_ships(character_id, limit=max(80, limit * 25))

    result = []

    for loss in losses:
        ship_type_id = loss.get("ship_type_id")
        if not ship_type_id:
            continue

        ship_name = get_ship_name(ship_type_id)

        if is_ignored_last_ship_name(ship_name):
            continue

        result.append(
            {
                "ship_type_id": ship_type_id,
                "name": ship_name,
                "display_name": shorten_ship_name(ship_name),
                "killmail_id": loss.get("killmail_id"),
                "killmail_time": loss.get("killmail_time"),
                "last_loss_url": loss.get("last_loss_url"),
            }
        )

        if len(result) >= limit:
            break

    return result


def shorten_ship_name(name: str) -> str:
    """Shorten ship names for the Last Ships column.

    Example:
    Ferox Navy Issue -> Ferox NI
    Omen Navy Issue  -> Omen NI
    """
    parts = str(name or "").split()

    if len(parts) <= 1:
        return str(name or "?")

    first = parts[0]
    suffix = "".join(part[0].upper() for part in parts[1:] if part)

    return f"{first} {suffix}".strip()


class PilotWorker(QRunnable):
    def __init__(self, row: int, pilot_name: str):
        super().__init__()

        self.row = row
        self.pilot_name = pilot_name
        self.signals = PilotWorkerSignals()

    def run(self):
        try:
            result = {
                "pilot": self.pilot_name,
                "character_id": None,
                "danger": 0,
                "gang": 0,
                "ally": "?",
                "cyno": False,
                "url": "pilot not found",
                "top_ships": [],
            }

            character_id = get_character_id(self.pilot_name)

            if not character_id:
                self.signals.finished.emit(self.row, result)
                return

            stats = get_zkill_stats(character_id)

            danger = stats.get("dangerRatio", 0) if stats else 0
            gang = stats.get("gangRatio", 0) if stats else 0
            top_ships = build_last_lost_ships(character_id, limit=3)
            ally = get_ally_or_corp(character_id)

            result.update(
                {
                    "character_id": character_id,
                    "danger": danger,
                    "gang": gang,
                    "ally": ally,
                    "cyno": False,
                    "url": f"https://zkillboard.com/character/{character_id}/",
                    "top_ships": top_ships,
                }
            )

            self.signals.finished.emit(self.row, result)

        except Exception as e:
            print(f"Worker error for {self.pilot_name}:", e)

            self.signals.finished.emit(
                self.row,
                {
                    "pilot": self.pilot_name,
                    "character_id": None,
                    "danger": 0,
                    "gang": 0,
                    "ally": "ERR",
                    "cyno": False,
                    "url": str(e),
                    "top_ships": [],
                },
            )


class CynoWorker(QRunnable):
    def __init__(self, row: int, character_id: int):
        super().__init__()

        self.row = row
        self.character_id = character_id
        self.signals = CynoWorkerSignals()

    def run(self):
        try:
            cyno = has_cyno_history(
                self.character_id, limit=10, days=40, max_killmails=5
            )

            self.signals.finished.emit(self.row, cyno)

        except Exception as e:
            print(f"Cyno worker error for {self.character_id}:", e)
            self.signals.finished.emit(self.row, False)
