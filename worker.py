from PySide6.QtCore import QObject, Signal, QRunnable

from esi_client import (
    get_character_id,
    get_ally_or_corp,
)

from zkill_client import (
    get_danger_percent,
    get_gangRatio,
    has_cyno_history,
)


class PilotWorkerSignals(QObject):
    finished = Signal(int, dict)


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
            }

            character_id = get_character_id(self.pilot_name)

            if not character_id:
                self.signals.finished.emit(
                    self.row,
                    result
                )
                return

            danger = get_danger_percent(character_id)
            gang = get_gangRatio(character_id)
            ally = get_ally_or_corp(character_id)

            cyno = has_cyno_history(
                character_id,
                limit=50,
                days=28
            )

            result.update({
                "character_id": character_id,
                "danger": danger,
                "gang": gang,
                "ally": ally,
                "cyno": cyno,
                "url": f"https://zkillboard.com/character/{character_id}/",
            })

            self.signals.finished.emit(
                self.row,
                result
            )

        except Exception as e:
            print(
                f"Worker error for {self.pilot_name}:",
                e
            )

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
                }
            )
