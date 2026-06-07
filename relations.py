from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal, QRunnable

from cache import cache
from zkill_client import get_recent_kills


KILL_LIMIT_PER_PILOT = 40
MAX_WORKERS = 20
TTL_RELATIONS = 300  # 5 минут


class RelationWorkerSignals(QObject):
    finished = Signal(object)


class RelationWorker(QRunnable):
    def __init__(self, row_character_ids: dict[int, int]):
        super().__init__()

        self.row_character_ids = row_character_ids
        self.signals = RelationWorkerSignals()

    def get_cache_key(self):
        ids = sorted(
            character_id
            for character_id in self.row_character_ids.values()
            if character_id
        )

        return "relations:v10:" + ",".join(str(x) for x in ids)

    def normalize_cached_relations(self, cached):
        if not isinstance(cached, dict):
            return {}

        normalized = {}

        for key, values in cached.items():
            try:
                character_id = int(key)
            except Exception:
                continue

            if not isinstance(values, list):
                continue

            clean_values = []

            for value in values:
                try:
                    clean_values.append(int(value))
                except Exception:
                    continue

            if clean_values:
                normalized[character_id] = clean_values

        return normalized

    def character_relations_to_row_relations(
        self,
        character_relations: dict[int, list[int]],
        character_to_row: dict[int, int],
    ):
        row_relations = {}

        for character_id, linked_ids in character_relations.items():
            row = character_to_row.get(character_id)

            if row is None:
                continue

            linked_rows = []

            for linked_id in linked_ids:
                linked_row = character_to_row.get(linked_id)

                if linked_row is None:
                    continue

                if linked_row == row:
                    continue

                linked_rows.append(linked_row)

            if linked_rows:
                row_relations[row] = sorted(set(linked_rows))

        return row_relations

    def load_recent_kills(self, character_id: int):
        kills = get_recent_kills(
            character_id,
            limit=KILL_LIMIT_PER_PILOT,
        )

        result = []

        for kill in kills:
            killmail_id = kill.get("killmail_id")
            zkb = kill.get("zkb", {})
            killmail_hash = zkb.get("hash")

            if not killmail_id:
                continue

            result.append(
                {
                    "killmail_id": killmail_id,
                    "hash": killmail_hash,
                    "character_id": character_id,
                }
            )

        return result

    def add_relation(self, relations, pilot_a, pilot_b):
        if pilot_a == pilot_b:
            return

        if pilot_a not in relations:
            relations[pilot_a] = set()

        if pilot_b not in relations:
            relations[pilot_b] = set()

        relations[pilot_a].add(pilot_b)
        relations[pilot_b].add(pilot_a)

    def add_group_relations(self, relations, pilots):
        pilots = list(pilots)

        if len(pilots) < 2:
            return

        for pilot_a in pilots:
            for pilot_b in pilots:
                if pilot_a == pilot_b:
                    continue

                self.add_relation(relations, pilot_a, pilot_b)

    def run(self):
        try:
            character_to_row = {
                character_id: row
                for row, character_id in self.row_character_ids.items()
                if character_id
            }

            local_ids = set(character_to_row.keys())

            if len(local_ids) < 2:
                self.signals.finished.emit({})
                return

            cache_key = self.get_cache_key()
            cached = cache.get(cache_key, ttl_seconds=TTL_RELATIONS)

            if cached is not None:
                cached_character_relations = self.normalize_cached_relations(cached)

                row_relations = self.character_relations_to_row_relations(
                    cached_character_relations,
                    character_to_row,
                )

                self.signals.finished.emit(row_relations)
                return

            character_relations = {character_id: set() for character_id in local_ids}

            killmail_owners = {}

            # Параллельно грузим recent kills всех локальных пилотов
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(self.load_recent_kills, character_id): character_id
                    for character_id in local_ids
                }

                for future in as_completed(futures):
                    try:
                        kills = future.result()
                    except Exception as e:
                        print("[RELATIONS] recent kills error:", e)
                        continue

                    for kill in kills:
                        killmail_id = kill["killmail_id"]
                        character_id = kill["character_id"]

                        if killmail_id not in killmail_owners:
                            killmail_owners[killmail_id] = set()

                        killmail_owners[killmail_id].add(character_id)

            # Если один и тот же killmail_id встречается у нескольких пилотов —
            # значит они участвовали в одном килле вместе
            for killmail_id, owners in killmail_owners.items():
                if len(owners) < 2:
                    continue

                self.add_group_relations(character_relations, owners)

            clean_character_relations = {
                character_id: sorted(list(linked_ids))
                for character_id, linked_ids in character_relations.items()
                if linked_ids
            }

            cache.set(cache_key, clean_character_relations)

            row_relations = self.character_relations_to_row_relations(
                clean_character_relations,
                character_to_row,
            )

            total_links = sum(len(v) for v in row_relations.values())
            print(f"[RELATIONS] done: {total_links} links")

            self.signals.finished.emit(row_relations)

        except Exception as e:
            print("[RELATIONS] ERROR:", e)
            self.signals.finished.emit({})
