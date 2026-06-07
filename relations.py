from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal, QRunnable

from cache import cache
from zkill_client import (
    get_recent_kills,
    get_full_killmail,
)

KILL_LIMIT_PER_PILOT = 8
MAX_FULL_KILLMAILS = 25
MAX_WORKERS = 10
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

        return "relations:" + ",".join(str(x) for x in ids)

    def load_recent_kills(self, character_id: int):
        kills = get_recent_kills(
            character_id,
            limit=KILL_LIMIT_PER_PILOT,
        )

        result = []

        for kill in kills:
            zkb = kill.get("zkb", {})

            # solo killmail не нужен для поиска напарников
            if zkb.get("solo") is True:
                continue

            killmail_id = kill.get("killmail_id")
            killmail_hash = zkb.get("hash")

            if not killmail_id or not killmail_hash:
                continue

            result.append(
                {
                    "killmail_id": killmail_id,
                    "hash": killmail_hash,
                }
            )

        return result

    def load_full_killmail(self, killmail):
        killmail_id = killmail["killmail_id"]
        killmail_hash = killmail["hash"]

        data = get_full_killmail(
            killmail_id,
            killmail_hash,
        )

        if not data:
            return None

        return {
            "killmail_id": killmail_id,
            "data": data,
        }

    def run(self):
        try:
            cache_key = self.get_cache_key()
            cached = cache.get(cache_key, ttl_seconds=TTL_RELATIONS)

            if cached is not None:
                print("[RELATIONS] cache hit")
                self.signals.finished.emit(cached)
                return

            character_to_row = {
                character_id: row
                for row, character_id in self.row_character_ids.items()
                if character_id
            }

            local_ids = set(character_to_row.keys())

            if len(local_ids) < 2:
                self.signals.finished.emit({})
                return

            relations = {row: set() for row in self.row_character_ids.keys()}

            all_killmails = {}

            # 1. Параллельно берём recent kills всех пилотов
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(self.load_recent_kills, character_id): character_id
                    for character_id in local_ids
                }

                for future in as_completed(futures):
                    try:
                        kills = future.result()
                    except Exception as e:
                        self.log("recent kills error:", e)
                        continue

                    for kill in kills:
                        all_killmails[kill["killmail_id"]] = kill

            if not all_killmails:
                cache.set(cache_key, {})
                self.signals.finished.emit({})
                return

            # 2. Сортируем от новых к старым и режем общий лимит
            sorted_killmails = sorted(
                all_killmails.values(),
                key=lambda item: item["killmail_id"],
                reverse=True,
            )

            limited_killmails = sorted_killmails[:MAX_FULL_KILLMAILS]

            self.log("unique killmails:", len(all_killmails))
            self.log("checking full killmails:", len(limited_killmails))

            full_killmails = []

            # 3. Параллельно грузим full killmail
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [
                    executor.submit(self.load_full_killmail, killmail)
                    for killmail in limited_killmails
                ]

                for future in as_completed(futures):
                    try:
                        result = future.result()
                    except Exception as e:
                        self.log("full killmail error:", e)
                        continue

                    if result:
                        full_killmails.append(result)

            # 4. Строим связи только между attackers из local
            for entry in full_killmails:
                killmail = entry["data"]

                local_attackers = set()

                for attacker in killmail.get("attackers", []):
                    attacker_id = attacker.get("character_id")

                    if attacker_id in local_ids:
                        local_attackers.add(attacker_id)

                if len(local_attackers) < 2:
                    continue

                for pilot_a in local_attackers:
                    row_a = character_to_row[pilot_a]

                    for pilot_b in local_attackers:
                        if pilot_a == pilot_b:
                            continue

                        row_b = character_to_row[pilot_b]
                        relations[row_a].add(row_b)

            clean_relations = {
                row: sorted(list(related_rows))
                for row, related_rows in relations.items()
                if related_rows
            }

            total_links = sum(len(v) for v in clean_relations.values())

            cache.set(cache_key, clean_relations)

            print(f"[RELATIONS] done: {total_links} links")

            self.signals.finished.emit(clean_relations)

        except Exception as e:
            print("[RELATIONS] ERROR:", e)
            self.signals.finished.emit({})
