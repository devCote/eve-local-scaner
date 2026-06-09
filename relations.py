from PySide6.QtCore import QObject, Signal, QRunnable

from cache import cache
from local_intel_db import get_linked_character_relations


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

        return "relations:local:v1:" + ",".join(str(x) for x in ids)

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

    def run(self):
        try:
            character_to_row = {
                character_id: row
                for row, character_id in self.row_character_ids.items()
                if character_id
            }

            local_ids = sorted(character_to_row.keys())

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

            # One local SQLite query for all pilots in local.
            character_relations = get_linked_character_relations(
                local_ids,
                limit_killmails=20000,
            )

            cache.set(cache_key, character_relations)

            row_relations = self.character_relations_to_row_relations(
                character_relations,
                character_to_row,
            )

            total_links = sum(len(v) for v in row_relations.values())
            print(f"[RELATIONS][LOCAL DB] done: {total_links} links")

            self.signals.finished.emit(row_relations)

        except Exception as e:
            print("[RELATIONS][LOCAL DB] ERROR:", e)
            self.signals.finished.emit({})
