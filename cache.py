import json
import time
import threading
from pathlib import Path

from paths import user_data_path


CACHE_FILE = user_data_path("cache.json")


def _json_safe(value):
    """Return value if JSON serializable, otherwise None marker.

    FileCache is stored as JSON. Binary data such as avatar bytes must not be
    written here; use a file cache for images instead.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        safe = []
        for item in value:
            safe_item = _json_safe(item)
            if safe_item is not _UNSAFE:
                safe.append(safe_item)
        return safe
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if not isinstance(key, (str, int, float, bool)):
                continue
            safe_item = _json_safe(item)
            if safe_item is not _UNSAFE:
                safe[str(key)] = safe_item
        return safe
    return _UNSAFE


_UNSAFE = object()


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
        safe_value = _json_safe(value)

        if safe_value is _UNSAFE:
            # Do not poison JSON cache with bytes/QPixmap/etc.
            return

        with self.lock:
            self.data[key] = {"created_at": time.time(), "value": safe_value}

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
