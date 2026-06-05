import requests

from PySide6.QtCore import QObject, Signal, QRunnable
from ship_names import get_ship_name

from esi_client import (
    get_character_id,
    get_ally_or_corp,
)

from zkill_client import (
    get_danger_percent,
    get_gangRatio,
    has_cyno_history,
)


ZKILL_API = "https://zkillboard.com/api"
ESI_API = "https://esi.evetech.net/latest"

HEADERS = {"User-Agent": "EVE-Local-Intel-Scanner"}


class PilotWorkerSignals(QObject):
    finished = Signal(int, dict)


def get_zkill_stats(character_id: int) -> dict:
    url = f"{ZKILL_API}/stats/characterID/{character_id}/"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=10,
    )

    if response.status_code != 200:
        return {}

    return response.json()


def get_top_ship_ids_from_stats(stats: dict, limit: int = 3) -> list[int]:
    top_all_time = stats.get("topAllTime", [])

    for block in top_all_time:
        if block.get("type") == "ship":
            ships = block.get("data", [])

            result = []

            for ship in ships[:limit]:
                ship_type_id = ship.get("shipTypeID")

                if ship_type_id:
                    result.append(ship_type_id)

            return result

    return []


def get_recent_losses(character_id: int, limit: int = 100) -> list[dict]:
    url = f"{ZKILL_API}/losses/characterID/{character_id}/"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=10,
    )

    if response.status_code != 200:
        return []

    losses = response.json()

    if not isinstance(losses, list):
        return []

    return losses[:limit]


def get_full_killmail(killmail_id: int, killmail_hash: str) -> dict:
    url = f"{ESI_API}/killmails/{killmail_id}/{killmail_hash}/"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=10,
    )

    if response.status_code != 200:
        return {}

    return response.json()


def find_last_loss_url_for_ship(
    character_id: int,
    ship_type_id: int,
    losses: list[dict],
) -> str | None:
    for loss in losses:
        killmail_id = loss.get("killmail_id")
        zkb = loss.get("zkb", {})
        killmail_hash = zkb.get("hash")

        if not killmail_id or not killmail_hash:
            continue

        killmail = get_full_killmail(
            killmail_id,
            killmail_hash,
        )

        victim = killmail.get("victim", {})
        victim_character_id = victim.get("character_id")
        victim_ship_type_id = victim.get("ship_type_id")

        if victim_character_id != character_id:
            continue

        if victim_ship_type_id == ship_type_id:
            return f"https://zkillboard.com/kill/{killmail_id}/"

    return None


def build_top_ships(character_id: int, stats: dict, limit: int = 3) -> list[dict]:
    top_ship_ids = get_top_ship_ids_from_stats(stats, limit=limit)

    top_ships = []

    for ship_type_id in top_ship_ids:
        top_ships.append(
            {
                "ship_type_id": ship_type_id,
                "name": get_ship_name(ship_type_id),
                "last_loss_url": None,
            }
        )

    return top_ships


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

            danger = stats.get("dangerRatio")
            gang = stats.get("gangRatio")

            if danger is None:
                danger = get_danger_percent(character_id)

            if gang is None:
                gang = get_gangRatio(character_id)

            ally = get_ally_or_corp(character_id)

            cyno = has_cyno_history(
                character_id,
                limit=50,
                days=28,
            )

            top_ships = build_top_ships(
                character_id=character_id,
                stats=stats,
                limit=3,
            )

            result.update(
                {
                    "character_id": character_id,
                    "danger": danger,
                    "gang": gang,
                    "ally": ally,
                    "cyno": cyno,
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
