from PySide6.QtCore import QObject, Signal, QRunnable

from ship_names import get_ship_name

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


def build_top_ships(stats: dict, limit: int = 3) -> list[dict]:
    top_ship_ids = get_top_ship_ids_from_stats(stats, limit=limit)

    result = []

    for ship_type_id in top_ship_ids:
        result.append(
            {
                "ship_type_id": ship_type_id,
                "name": get_ship_name(ship_type_id),
                "last_loss_url": None,
            }
        )

    return result


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
            top_ships = build_top_ships(stats, limit=3)
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
                self.character_id, limit=10, days=28, max_killmails=5
            )

            self.signals.finished.emit(self.row, cyno)

        except Exception as e:
            print(f"Cyno worker error for {self.character_id}:", e)
            self.signals.finished.emit(self.row, False)
