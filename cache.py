import json
import time
import threading
from pathlib import Path

from paths import user_data_path


CACHE_FILE = user_data_path("cache.json")


class FileCache:
    def __init__(self, filename=CACHE_FILE):
        self.filename = Path(filename)
        self.lock = threading.RLock()
        self.data = self.load()

    def load(self):
        if not self.filename.exists():
            return {}

        try:
            with self.filename.open("r", encoding="utf-8") as file:
                data = json.load(file)

            return data if isinstance(data, dict) else {}

        except Exception:
            return {}

    def save(self):
        try:
            with self.lock:
                self.filename.parent.mkdir(parents=True, exist_ok=True)
                data_copy = dict(self.data)
                tmp_path = self.filename.with_suffix(self.filename.suffix + ".tmp")

                with tmp_path.open("w", encoding="utf-8") as file:
                    json.dump(data_copy, file, ensure_ascii=False, indent=2)

                tmp_path.replace(self.filename)

        except Exception as e:
            print("Cache save error:", e)

    def get(self, key: str, ttl_seconds: int):
        with self.lock:
            item = self.data.get(key)

            if not item:
                return None

            created_at = item.get("created_at", 0)

            try:
                created_at = float(created_at)
            except Exception:
                return None

            if time.time() - created_at > ttl_seconds:
                return None

            return item.get("value")

    def set(self, key: str, value):
        with self.lock:
            self.data[key] = {"created_at": time.time(), "value": value}

        self.save()

    def clear_expired(self, ttl_seconds: int = 7 * 24 * 3600):
        now = time.time()

        with self.lock:
            keys_to_delete = [
                key
                for key, item in self.data.items()
                if now - float(item.get("created_at", 0) or 0) > ttl_seconds
            ]

            for key in keys_to_delete:
                self.data.pop(key, None)

        if keys_to_delete:
            self.save()


cache = FileCache()
