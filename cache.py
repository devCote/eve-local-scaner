import json
import os
import time
import threading


CACHE_FILE = "cache.json"


class FileCache:
    def __init__(self, filename=CACHE_FILE):
        self.filename = filename
        self.lock = threading.Lock()
        self.data = self.load()

    def load(self):
        if not os.path.exists(self.filename):
            return {}

        try:
            with open(self.filename, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return {}

    def save(self):
        try:
            with self.lock:
                data_copy = dict(self.data)

                with open(self.filename, "w", encoding="utf-8") as file:
                    json.dump(data_copy, file, ensure_ascii=False, indent=2)

        except Exception as e:
            print("Cache save error:", e)

    def get(self, key: str, ttl_seconds: int):
        with self.lock:
            item = self.data.get(key)

            if not item:
                return None

            created_at = item.get("created_at", 0)

            if time.time() - created_at > ttl_seconds:
                return None

            return item.get("value")

    def set(self, key: str, value):
        with self.lock:
            self.data[key] = {
                "created_at": time.time(),
                "value": value
            }

        self.save()


cache = FileCache()
