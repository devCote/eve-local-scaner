"""Background data loader for the native zKill fitting popup."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal

from app_http_client import get_bytes, get_json, post_json
from cache import cache
from local_intel_db import get_killmail_detail
from type_names import get_local_type_name
from zkill_client import TIMEOUT, USER_AGENT
from zkill_fit_utils import (
    FITTING_TTL_SECONDS,
    HIGH_FLAGS,
    IMAGE_CACHE_DIR,
    LOW_FLAGS,
    MID_FLAGS,
    RIG_FLAGS,
    SUBSYSTEM_FLAGS,
    safe_int,
)


def _image_cache_path(kind: str, type_id: int, size: int):
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGE_CACHE_DIR / f"{kind}_{int(type_id)}_{int(size)}.png"


def _download_image_bytes(url: str, cache_path) -> bytes:
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes()

    data = get_bytes(url, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
    if data:
        cache_path.write_bytes(data)
    return data


def _download_type_icon(type_id: int, size: int = 64) -> bytes:
    type_id = int(type_id)
    cache_path = _image_cache_path("icon", type_id, size)
    url = f"https://images.evetech.net/types/{type_id}/icon?size={size}"
    return _download_image_bytes(url, cache_path)


def _download_ship_render(type_id: int, size: int = 256) -> bytes:
    type_id = int(type_id)
    cache_path = _image_cache_path("render", type_id, size)
    url = f"https://images.evetech.net/types/{type_id}/render?size={size}"
    try:
        return _download_image_bytes(url, cache_path)
    except Exception:
        return _download_type_icon(type_id, size)


def _download_zkill_panel_image(name: str) -> bytes:
    safe_name = str(name).replace("/", "_").replace("\\", "_")
    cache_path = _image_cache_path("zkbpanel", abs(hash(safe_name)) % 10_000_000, 398)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes()

    url = f"https://zkillboard.com/img/panel/{name}"
    return _download_image_bytes(url, cache_path)


def _classify_slot(flag: int) -> str | None:
    if flag in HIGH_FLAGS:
        return "high"
    if flag in MID_FLAGS:
        return "mid"
    if flag in LOW_FLAGS:
        return "low"
    if flag in RIG_FLAGS:
        return "rig"
    if flag in SUBSYSTEM_FLAGS:
        return "subsystem"
    return None


def _extract_fit_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "high": [],
        "mid": [],
        "low": [],
        "rig": [],
        "subsystem": [],
    }
    grouped_slots: dict[str, dict[int, dict[str, Any]]] = {
        "high": {},
        "mid": {},
        "low": {},
    }

    for item in items or []:
        if not isinstance(item, dict):
            continue

        type_id = safe_int(item.get("item_type_id"))
        flag = safe_int(item.get("flag"))
        slot = _classify_slot(flag)
        if not type_id or not slot:
            continue

        children = item.get("items") or []
        charge_type_id = 0
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict) and child.get("item_type_id"):
                    charge_type_id = safe_int(child.get("item_type_id"))
                    break

        slot_base = {
            "low": 11,
            "mid": 19,
            "high": 27,
            "rig": 92,
            "subsystem": 125,
        }.get(slot, flag)
        slot_index = max(0, flag - slot_base)
        quantity = safe_int(item.get("quantity_destroyed") or item.get("quantity_dropped"), 1)
        row = {
            "type_id": type_id,
            "flag": flag,
            "slot_index": slot_index,
            "charge_type_id": charge_type_id,
            "quantity": quantity,
        }

        if slot in ("rig", "subsystem"):
            result[slot].append(row)
            continue

        bucket = grouped_slots[slot]
        existing = bucket.get(slot_index)
        if existing is None:
            bucket[slot_index] = row
            continue

        existing_is_module = safe_int(existing.get("quantity"), 1) == 1
        current_is_module = quantity == 1

        if current_is_module and not existing_is_module:
            if not row.get("charge_type_id") and existing.get("type_id"):
                row["charge_type_id"] = safe_int(existing.get("type_id"))
            bucket[slot_index] = row
        elif existing_is_module and not current_is_module:
            if not existing.get("charge_type_id"):
                existing["charge_type_id"] = type_id
        else:
            if not existing.get("charge_type_id") and type_id != safe_int(existing.get("type_id")):
                existing["charge_type_id"] = type_id

    for slot in ("high", "mid", "low"):
        rows = list(grouped_slots[slot].values())
        rows.sort(key=lambda row: int(row.get("flag") or 0))
        result[slot].extend(rows)

    for key in ("rig", "subsystem"):
        result[key].sort(key=lambda row: int(row.get("flag") or 0))
    return result


def _resolve_killmail_hash(killmail_id: int, row_data: dict[str, Any]) -> str:
    zkb = row_data.get("zkb") if isinstance(row_data.get("zkb"), dict) else {}
    direct = row_data.get("hash") or row_data.get("killmail_hash") or zkb.get("hash")
    if direct:
        return str(direct)

    cache_key = f"zkill:kill_hash:{int(killmail_id)}"
    cached = cache.get(cache_key, ttl_seconds=FITTING_TTL_SECONDS)
    if cached:
        return str(cached)

    url = f"https://zkillboard.com/api/killID/{int(killmail_id)}/"
    data = get_json(url, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
    if isinstance(data, list) and data:
        zkb = data[0].get("zkb") if isinstance(data[0], dict) else {}
        kill_hash = zkb.get("hash") if isinstance(zkb, dict) else None
        if kill_hash:
            cache.set(cache_key, str(kill_hash))
            return str(kill_hash)

    raise RuntimeError("Could not resolve killmail hash.")


def _load_full_killmail(killmail_id: int, killmail_hash: str) -> dict[str, Any]:
    cache_key = f"esi:killmail_full:{int(killmail_id)}:{killmail_hash}"
    cached = cache.get(cache_key, ttl_seconds=FITTING_TTL_SECONDS)
    if isinstance(cached, dict):
        return cached

    url = f"https://esi.evetech.net/latest/killmails/{int(killmail_id)}/{killmail_hash}/?datasource=tranquility"
    data = get_json(url, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
    if isinstance(data, dict):
        cache.set(cache_key, data)
        return data
    raise RuntimeError("ESI returned invalid killmail data.")


def _load_zkb_kill_summary(killmail_id: int, row_data: dict[str, Any]) -> dict[str, Any]:
    zkb = row_data.get("zkb") if isinstance(row_data.get("zkb"), dict) else {}
    if zkb and any(key in zkb for key in ("destroyedValue", "droppedValue", "totalValue")):
        return dict(zkb)

    cache_key = f"zkill:kill_summary:{int(killmail_id)}"
    cached = cache.get(cache_key, ttl_seconds=FITTING_TTL_SECONDS)
    if isinstance(cached, dict):
        return cached

    url = f"https://zkillboard.com/api/killID/{int(killmail_id)}/"
    data = get_json(url, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        zkb = data[0].get("zkb") if isinstance(data[0].get("zkb"), dict) else {}
        if isinstance(zkb, dict):
            cache.set(cache_key, zkb)
            return dict(zkb)
    return {}


def _resolve_single_type_name(type_id: int) -> str:
    """Resolve ships, modules and structures by ESI /universe/types/{type_id}/.

    /universe/names is fast for most items, but structures sometimes still end
    up as "Type 33475" in the popup if the bulk call fails or returns nothing.
    This fallback resolves those inventory type ids directly.
    """
    type_id = safe_int(type_id)
    if not type_id:
        return ""

    local_name = get_local_type_name(type_id)
    if local_name:
        return local_name

    for cache_key in (f"esi:type_name:{type_id}", f"esi:type-name:{type_id}"):
        cached = cache.get(cache_key, ttl_seconds=30 * 24 * 3600)
        if cached and not str(cached).strip().lower().startswith("type "):
            return str(cached)

    try:
        url = f"https://esi.evetech.net/latest/universe/types/{int(type_id)}/?datasource=tranquility"
        data = get_json(url, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
        if isinstance(data, dict):
            name = str(data.get("name") or "").strip()
            if name:
                cache.set(f"esi:type_name:{type_id}", name)
                cache.set(f"esi:type-name:{type_id}", name)
                return name
    except Exception:
        pass

    return ""


def _resolve_type_names(type_ids: list[int]) -> dict[int, str]:
    ids = sorted({int(t) for t in (type_ids or []) if int(t or 0) > 0})
    if not ids:
        return {}

    result: dict[int, str] = {}
    missing: list[int] = []
    for type_id in ids:
        local_name = get_local_type_name(type_id)
        if local_name:
            result[type_id] = local_name
            continue

        cached = cache.get(f"esi:type_name:{type_id}", ttl_seconds=30 * 24 * 3600)
        if cached and not str(cached).strip().lower().startswith("type "):
            result[type_id] = str(cached)
        else:
            missing.append(type_id)

    if missing:
        try:
            url = "https://esi.evetech.net/latest/universe/names/?datasource=tranquility"
            data = post_json(url, missing, user_agent=USER_AGENT, timeout=TIMEOUT, retries=1)
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict):
                        tid = safe_int(row.get("id"))
                        name = str(row.get("name") or "").strip()
                        if tid and name and not name.lower().startswith("type "):
                            result[tid] = name
                            cache.set(f"esi:type_name:{tid}", name)
                            cache.set(f"esi:type-name:{tid}", name)
        except Exception:
            pass

    # Direct fallback for any still-missing type. This is what fixes structures
    # like Mobile Depot / Upwell structures showing as "Type 33475".
    for type_id in ids:
        if type_id not in result:
            name = _resolve_single_type_name(type_id)
            if name:
                result[type_id] = name

    for type_id in ids:
        result.setdefault(type_id, f"Type {type_id}")
    return result



def _load_local_killmail_for_popup(killmail_id: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return (killmail, zkb_summary) from local SQLite details if available."""
    try:
        detail = get_killmail_detail(int(killmail_id))
    except Exception:
        detail = None

    if not isinstance(detail, dict):
        return None

    killmail = detail.get("killmail")
    if not isinstance(killmail, dict) or not killmail.get("victim"):
        return None

    zkb = detail.get("zkb") if isinstance(detail.get("zkb"), dict) else {}
    if not isinstance(zkb, dict):
        zkb = {}

    # Ensure values exist even if zkb_json was empty.
    for key, detail_key in (
        ("destroyedValue", "destroyed_value"),
        ("droppedValue", "dropped_value"),
        ("totalValue", "total_value"),
    ):
        if key not in zkb and detail.get(detail_key) is not None:
            zkb[key] = detail.get(detail_key)

    if detail.get("killmail_hash") and "hash" not in zkb:
        zkb["hash"] = detail.get("killmail_hash")

    return killmail, zkb


class NativeFitFetchThread(QThread):
    loaded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, row_data: dict[str, Any], request_id: int, parent=None):
        super().__init__(parent)
        self.row_data = dict(row_data or {})
        self.request_id = int(request_id)

    def run(self):
        killmail_id = safe_int(self.row_data.get("killmail_id"))
        if not killmail_id:
            self.failed.emit(self.request_id, "No killmail id.")
            return

        try:
            local_payload = _load_local_killmail_for_popup(killmail_id)
            if local_payload:
                killmail, zkb_summary = local_payload
            else:
                kill_hash = _resolve_killmail_hash(killmail_id, self.row_data)
                killmail = _load_full_killmail(killmail_id, kill_hash)
                zkb_summary = _load_zkb_kill_summary(killmail_id, self.row_data)

            victim = killmail.get("victim") if isinstance(killmail.get("victim"), dict) else {}
            ship_type_id = safe_int(victim.get("ship_type_id") or self.row_data.get("ship_type_id"))
            fit_items = _extract_fit_items(victim.get("items") or [])
            damage_taken = safe_int(victim.get("damage_taken"), 0)

            icon_type_ids: set[int] = set()
            for slot_rows in fit_items.values():
                for row in slot_rows:
                    if row.get("type_id"):
                        icon_type_ids.add(int(row["type_id"]))
                    if row.get("charge_type_id"):
                        icon_type_ids.add(int(row["charge_type_id"]))

            images: dict[int, bytes] = {}
            for type_id in sorted(icon_type_ids):
                if self.isInterruptionRequested():
                    return
                try:
                    images[type_id] = _download_type_icon(type_id, 64)
                except Exception:
                    images[type_id] = b""

            type_names = _resolve_type_names([ship_type_id, *sorted(icon_type_ids)])

            ship_bytes = b""
            if ship_type_id:
                try:
                    ship_bytes = _download_ship_render(ship_type_id, 256)
                except Exception:
                    ship_bytes = b""

            panel_images: dict[str, bytes] = {}
            for panel_name in ("tyrannis.png", "8h.png", "5m.png", "7l.png", "3r.png"):
                if self.isInterruptionRequested():
                    return
                try:
                    panel_images[panel_name] = _download_zkill_panel_image(panel_name)
                except Exception:
                    panel_images[panel_name] = b""

            row_ship_name = str(self.row_data.get("ship_name") or "").strip()
            resolved_ship_name = str(type_names.get(ship_type_id) or "").strip()
            if not row_ship_name or row_ship_name.lower().startswith("type "):
                row_ship_name = resolved_ship_name or row_ship_name or "Ship"

            self.loaded.emit(self.request_id, {
                "killmail_id": killmail_id,
                "ship_name": row_ship_name,
                "ship_type_id": ship_type_id,
                "ship_image": ship_bytes,
                "items": fit_items,
                "images": images,
                "type_names": type_names,
                "panel_images": panel_images,
                "damage_taken": damage_taken,
                "destroyed_value": zkb_summary.get("destroyedValue", 0),
                "dropped_value": zkb_summary.get("droppedValue", 0),
                "total_value": zkb_summary.get("totalValue", 0),
            })
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))
