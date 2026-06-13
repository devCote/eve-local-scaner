"""Native transparent zKill fitting popup.

This popup does NOT embed a browser and does NOT render zKillboard HTML.
It uses API data to build a local EVE-style circular fit view inside Qt.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import QPoint, QRectF, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from cache import cache
from paths import user_data_path
from zkill_client import TIMEOUT, USER_AGENT
from user_settings import load_ui_settings
from windows_blur import enable_eve_blur


FITTING_TTL_SECONDS = 24 * 3600
IMAGE_CACHE_DIR = user_data_path(Path("cache") / "eve_images")


def _transparency_to_alpha(transparency: int) -> int:
    transparency = max(0, min(100, int(transparency)))
    if transparency >= 99:
        transparency = 99
    return int(round(255 * (100 - transparency) / 100))


# EVE inventory flags used by fitted modules.
LOW_FLAGS = set(range(11, 19))        # LoSlot0..LoSlot7
MID_FLAGS = set(range(19, 27))        # MedSlot0..MedSlot7
HIGH_FLAGS = set(range(27, 35))       # HiSlot0..HiSlot7
RIG_FLAGS = set(range(92, 100))       # RigSlot0..RigSlot7
SUBSYSTEM_FLAGS = set(range(125, 133))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _image_cache_path(kind: str, type_id: int, size: int) -> Path:
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGE_CACHE_DIR / f"{kind}_{int(type_id)}_{int(size)}.png"


def _download_image_bytes(url: str, cache_path: Path) -> bytes:
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes()

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.content or b""
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
        # Some types do not have a render. Fall back to the icon endpoint.
        return _download_type_icon(type_id, size)


def _download_zkill_panel_image(name: str) -> bytes:
    """Download one transparent zKill fitting panel asset, cached locally.

    This is not a browser render and does not load the zKill page; it only
    reuses the same transparent PNG assets zKill uses for the fitting panel.
    """
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

    # For high/mid/low slots ESI may include both the fitted module and an
    # extra charge/ammo item with the SAME slot flag. We must not let the ammo
    # replace the module in the visible slot. So we group by slot index and keep
    # one primary module per slot, optionally attaching a charge_type_id.
    grouped_slots: dict[str, dict[int, dict[str, Any]]] = {
        "high": {},
        "mid": {},
        "low": {},
    }

    for item in items or []:
        if not isinstance(item, dict):
            continue

        type_id = _safe_int(item.get("item_type_id"))
        flag = _safe_int(item.get("flag"))
        slot = _classify_slot(flag)
        if not type_id or not slot:
            continue

        children = item.get("items") or []
        charge_type_id = 0
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict) and child.get("item_type_id"):
                    charge_type_id = _safe_int(child.get("item_type_id"))
                    break

        slot_base = {
            "low": 11,
            "mid": 19,
            "high": 27,
            "rig": 92,
            "subsystem": 125,
        }.get(slot, flag)
        slot_index = max(0, flag - slot_base)
        quantity = _safe_int(item.get("quantity_destroyed") or item.get("quantity_dropped"), 1)
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

        # Prefer a quantity==1 row as the real fitted module.
        existing_is_module = _safe_int(existing.get("quantity"), 1) == 1
        current_is_module = quantity == 1

        if current_is_module and not existing_is_module:
            # The old one was probably ammo/charge. Promote current as module
            # and keep old type_id as charge if current has none yet.
            if not row.get("charge_type_id") and existing.get("type_id"):
                row["charge_type_id"] = _safe_int(existing.get("type_id"))
            bucket[slot_index] = row
        elif existing_is_module and not current_is_module:
            # Existing is the module; current is probably the ammo/charge.
            if not existing.get("charge_type_id"):
                existing["charge_type_id"] = type_id
        else:
            # Fallback: keep the first item as the visible module, but if it has
            # no charge yet, attach the later item's type_id as charge.
            if not existing.get("charge_type_id") and type_id != _safe_int(existing.get("type_id")):
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
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
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
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        cache.set(cache_key, data)
        return data
    raise RuntimeError("ESI returned invalid killmail data.")


def _load_zkb_kill_summary(killmail_id: int, row_data: dict[str, Any]) -> dict[str, Any]:
    """Return zKB monetary summary for one killmail."""
    zkb = row_data.get("zkb") if isinstance(row_data.get("zkb"), dict) else {}
    if zkb and any(key in zkb for key in ("destroyedValue", "droppedValue", "totalValue")):
        return dict(zkb)

    cache_key = f"zkill:kill_summary:{int(killmail_id)}"
    cached = cache.get(cache_key, ttl_seconds=FITTING_TTL_SECONDS)
    if isinstance(cached, dict):
        return cached

    url = f"https://zkillboard.com/api/killID/{int(killmail_id)}/"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        zkb = data[0].get("zkb") if isinstance(data[0].get("zkb"), dict) else {}
        if isinstance(zkb, dict):
            cache.set(cache_key, zkb)
            return dict(zkb)
    return {}


def _format_isk_short(value: Any) -> str:
    try:
        num = float(value or 0)
    except Exception:
        return "-"
    abs_num = abs(num)
    if abs_num >= 1_000_000_000:
        out = f"{num / 1_000_000_000:.2f}".replace('.', ',')
        return f"{out}b ISK"
    if abs_num >= 1_000_000:
        out = f"{num / 1_000_000:.2f}".replace('.', ',')
        return f"{out}m ISK"
    if abs_num >= 1_000:
        out = f"{num / 1_000:.2f}".replace('.', ',')
        return f"{out}k ISK"
    out = f"{num:.0f}".replace('.', ',')
    return f"{out} ISK"


def _resolve_type_names(type_ids: list[int]) -> dict[int, str]:
    ids = sorted({int(t) for t in (type_ids or []) if int(t or 0) > 0})
    if not ids:
        return {}

    result: dict[int, str] = {}
    missing: list[int] = []
    for type_id in ids:
        cached = cache.get(f"esi:type_name:{type_id}", ttl_seconds=30 * 24 * 3600)
        if cached:
            result[type_id] = str(cached)
        else:
            missing.append(type_id)

    if missing:
        try:
            url = "https://esi.evetech.net/latest/universe/names/?datasource=tranquility"
            response = requests.post(url, json=missing, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict):
                        tid = _safe_int(row.get("id"))
                        name = str(row.get("name") or "").strip()
                        if tid and name:
                            result[tid] = name
                            cache.set(f"esi:type_name:{tid}", name)
        except Exception:
            pass

    # fallback names for any unresolved ids
    for type_id in ids:
        result.setdefault(type_id, f"Type {type_id}")
    return result


def _build_eft_fit_text(fit_data: dict[str, Any], row_data: dict[str, Any]) -> str:
    ship_name = str(fit_data.get("ship_name") or row_data.get("ship_name") or "Ship")
    items = fit_data.get("items") if isinstance(fit_data.get("items"), dict) else {}
    type_names = fit_data.get("type_names") if isinstance(fit_data.get("type_names"), dict) else {}

    def name_for(type_id: int) -> str:
        return str(type_names.get(int(type_id), f"Type {int(type_id)}"))

    lines: list[str] = [f"[{ship_name}, zKill Fit]", ""]

    for slot in ("low", "mid", "high"):
        slot_items = list(items.get(slot) or [])
        slot_items.sort(key=lambda row: int(row.get("slot_index") or 0))
        for row in slot_items:
            lines.append(name_for(_safe_int(row.get("type_id"))))
        lines.append("")

    for slot in ("rig", "subsystem"):
        slot_items = list(items.get(slot) or [])
        slot_items.sort(key=lambda row: int(row.get("slot_index") or 0))
        for row in slot_items:
            lines.append(name_for(_safe_int(row.get("type_id"))))
        if slot_items:
            lines.append("")

    charges: list[str] = []
    for slot in ("high", "mid", "low"):
        for row in list(items.get(slot) or []):
            charge_id = _safe_int(row.get("charge_type_id"))
            if charge_id:
                charges.append(name_for(charge_id))
    if charges:
        for charge_name in charges:
            lines.append(f"{charge_name} x1")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


class NativeFitFetchThread(QThread):
    loaded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, row_data: dict[str, Any], request_id: int, parent=None):
        super().__init__(parent)
        self.row_data = dict(row_data or {})
        self.request_id = int(request_id)

    def run(self):
        killmail_id = _safe_int(self.row_data.get("killmail_id"))
        if not killmail_id:
            self.failed.emit(self.request_id, "No killmail id.")
            return

        try:
            kill_hash = _resolve_killmail_hash(killmail_id, self.row_data)
            killmail = _load_full_killmail(killmail_id, kill_hash)
            zkb_summary = _load_zkb_kill_summary(killmail_id, self.row_data)
            victim = killmail.get("victim") if isinstance(killmail.get("victim"), dict) else {}
            ship_type_id = _safe_int(victim.get("ship_type_id") or self.row_data.get("ship_type_id"))
            fit_items = _extract_fit_items(victim.get("items") or [])
            damage_taken = _safe_int(victim.get("damage_taken"), 0)

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

            self.loaded.emit(self.request_id, {
                "killmail_id": killmail_id,
                "ship_name": self.row_data.get("ship_name") or "Ship",
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


class FittingPanelPopup(QFrame):
    """Transparent native EVE-style fitting popup near the app top-right."""

    mouseLeft = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setObjectName("NativeFittingPanelPopup")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._request_id = 0
        self._thread: NativeFitFetchThread | None = None
        self._row_data: dict[str, Any] = {}
        self._fit_data: dict[str, Any] | None = None
        self._error = ""
        self._loading = False
        self._pixmaps: dict[int, QPixmap] = {}
        self._ship_pixmap = QPixmap()
        self._panel_pixmaps: dict[str, QPixmap] = {}
        self._pinned = False
        self._mouse_inside = False
        self._hover_hitboxes: list[tuple[QRectF, str]] = []
        self._hovered_module_name = ""
        self._loading_phase = 0.0
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(55)
        self._loading_timer.timeout.connect(self._advance_loading_animation)

        # Visual settings copied from the main app at show time.
        settings = load_ui_settings()
        self._ui_transparency = int(settings.get("transparency", 10))
        self._ui_alpha = _transparency_to_alpha(self._ui_transparency)
        self._ui_blur = int(settings.get("blur", 0))
        self._ui_bg_color = str(settings.get("bg_color", "#0b0b0b"))
        self._ui_frame_color = str(settings.get("frame_color", "#161616"))

        self.setFixedSize(398, 398)
        self._apply_circle_mask()

        self.save_fit_button = QPushButton("Save Fit", self)
        self.save_fit_button.setCursor(Qt.PointingHandCursor)
        self.save_fit_button.clicked.connect(self._copy_fit_to_clipboard)
        self.save_fit_button.setStyleSheet(
            "QPushButton {"
            "background-color: rgba(0, 0, 0, 0);"
            "color: rgb(195, 245, 255); border: 1px solid rgba(0, 220, 255, 185);"
            "border-radius: 5px; padding: 1px 10px; font-size: 10px; font-weight: 600; }"
            "QPushButton:hover { background-color: rgba(0, 210, 255, 38); border: 1px solid rgba(80, 235, 255, 230); color: white; }"
            "QPushButton:pressed { background-color: rgba(0, 210, 255, 62); }"
        )
        self.save_fit_button.hide()

    def _advance_loading_animation(self):
        if not self._loading:
            self._loading_timer.stop()
            return
        self._loading_phase = (self._loading_phase + 0.18) % (math.pi * 2)
        self.update()

    def _apply_circle_mask(self):
        # Use a strict circular mask so nothing is visible outside the outer ring.
        margin = 6
        self.setMask(QRegion(self.rect().adjusted(margin, margin, -margin, -margin), QRegion.Ellipse))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_circle_mask()
        self._layout_button()

    def _layout_button(self):
        self.save_fit_button.setGeometry(144, 94, 110, 24)

    def _copy_fit_to_clipboard(self):
        fit_data = self._fit_data if isinstance(self._fit_data, dict) else {}
        row_data = self._row_data if isinstance(self._row_data, dict) else {}
        text = _build_eft_fit_text(fit_data, row_data)
        QApplication.clipboard().setText(text)

    def _type_name(self, type_id: int) -> str:
        fit_data = self._fit_data if isinstance(self._fit_data, dict) else {}
        type_names = fit_data.get("type_names") if isinstance(fit_data.get("type_names"), dict) else {}
        return str(type_names.get(int(type_id), f"Type {int(type_id)}"))

    def show_for_row(self, row_data: dict, owner_widget, pinned: bool = False):
        killmail_id = _safe_int((row_data or {}).get("killmail_id"))
        if not killmail_id:
            self.hide()
            return

        self._row_data = dict(row_data or {})
        self._pinned = bool(pinned)
        self._mouse_inside = False
        self._request_id += 1
        request_id = self._request_id
        self._fit_data = None
        self._error = ""
        self._loading = True
        self._loading_phase = 0.0
        self._hover_hitboxes = []
        self._hovered_module_name = ""
        self._loading_timer.start()
        self._pixmaps = {}
        self._ship_pixmap = QPixmap()
        self._panel_pixmaps = {}
        self._apply_owner_visual_settings(owner_widget)
        self._apply_circle_mask()
        self._layout_button()
        self._move_near_owner(owner_widget)
        self.show()
        QTimer.singleShot(0, self._apply_window_blur)
        QTimer.singleShot(80, self._apply_window_blur)
        self.save_fit_button.hide()
        self.update()

        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()

        self._thread = NativeFitFetchThread(self._row_data, request_id, self)
        self._thread.loaded.connect(self._on_loaded)
        self._thread.failed.connect(self._on_failed)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _apply_owner_visual_settings(self, owner_widget):
        """Copy transparency/blur/background from the main app window."""
        window = owner_widget.window() if owner_widget else None

        transparency = getattr(window, "ui_transparency", None)
        alpha = getattr(window, "ui_alpha", None)
        blur = getattr(window, "ui_blur", None)
        bg_color = getattr(window, "ui_bg_color", None)
        frame_color = getattr(window, "ui_frame_color", None)

        if transparency is None or alpha is None:
            settings = load_ui_settings()
            transparency = settings.get("transparency", self._ui_transparency)
            alpha = _transparency_to_alpha(int(transparency))
            blur = settings.get("blur", self._ui_blur)
            bg_color = settings.get("bg_color", self._ui_bg_color)
            frame_color = settings.get("frame_color", self._ui_frame_color)

        self._ui_transparency = max(0, min(100, int(transparency)))
        self._ui_alpha = max(0, min(255, int(alpha)))
        self._ui_blur = 1 if int(blur or 0) else 0
        self._ui_bg_color = str(bg_color or "#0b0b0b")
        self._ui_frame_color = str(frame_color or "#161616")

    def _bg_rgb(self):
        color = QColor(self._ui_bg_color)
        return (color.red(), color.green(), color.blue())

    def _apply_window_blur(self):
        try:
            # Windows acrylic blur is always applied to the full rectangular
            # window surface and ignores the circular visual composition. For a
            # truly round fitting popup, keep the popup masked/transparent and
            # disable acrylic on this window specifically.
            enable_eve_blur(
                int(self.winId()),
                panel_alpha=self._ui_alpha,
                blur_percent=0,
                rgb=self._bg_rgb(),
            )
        except Exception as exc:
            print("Fit popup blur apply error:", exc)

    def is_pinned(self) -> bool:
        return bool(self._pinned)

    def hide_panel(self, force: bool = False):
        if not force and (self._pinned or self._mouse_inside):
            return
        self._pinned = False
        self._mouse_inside = False
        self._loading_timer.stop()
        self.hide()

    def enterEvent(self, event):
        self._mouse_inside = True
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position()
        hover_name = ""
        for rect, name in self._hover_hitboxes:
            if rect.contains(pos):
                hover_name = str(name)
                break
        if hover_name != self._hovered_module_name:
            self._hovered_module_name = hover_name
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._mouse_inside = False
        self._hovered_module_name = ""
        # When the user pinned the popup by clicking a ship, leaving the popup
        # is the explicit close event.
        self.hide_panel(force=True)
        self.mouseLeft.emit()
        super().leaveEvent(event)

    def _move_near_owner(self, owner_widget):
        window = owner_widget.window() if owner_widget else None
        if window:
            geo = window.frameGeometry()
            pos = QPoint(geo.right() + 8, geo.top() - 18)
        else:
            pos = QApplication.instance().activeWindow().pos() if QApplication.instance().activeWindow() else QPoint(20, 20)

        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            if pos.x() + self.width() > available.right():
                pos.setX(max(available.left(), (window.frameGeometry().left() - self.width() - 8) if window else available.right() - self.width()))
            if pos.y() < available.top():
                pos.setY(available.top())
            if pos.y() + self.height() > available.bottom():
                pos.setY(max(available.top(), available.bottom() - self.height()))
        self.move(pos)

    def _on_loaded(self, request_id: int, data: object):
        if request_id != self._request_id:
            return
        self._loading = False
        self._loading_timer.stop()
        self._error = ""
        self._fit_data = data if isinstance(data, dict) else {}
        self._pixmaps = {}

        for type_id, raw in (self._fit_data.get("images") or {}).items():
            pixmap = QPixmap()
            if raw:
                pixmap.loadFromData(raw)
            self._pixmaps[int(type_id)] = pixmap

        self._ship_pixmap = QPixmap()
        ship_raw = self._fit_data.get("ship_image") or b""
        if ship_raw:
            self._ship_pixmap.loadFromData(ship_raw)

        self._panel_pixmaps = {}
        for name, raw in (self._fit_data.get("panel_images") or {}).items():
            pixmap = QPixmap()
            if raw:
                pixmap.loadFromData(raw)
            self._panel_pixmaps[str(name)] = pixmap

        self.save_fit_button.show()
        self.update()

    def _on_failed(self, request_id: int, error: str):
        if request_id != self._request_id:
            return
        self._loading = False
        self._loading_timer.stop()
        self._fit_data = None
        self._error = str(error or "Could not load fitting.")
        self._hover_hitboxes = []
        self._hovered_module_name = ""
        self.save_fit_button.hide()
        self.update()

    def _cleanup_thread(self):
        thread = self.sender()
        if thread:
            thread.deleteLater()
        if thread is self._thread:
            self._thread = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = self.rect().adjusted(0, 0, 0, 0)

        # Circular popup background uses the same transparency/bg/frame settings
        # as the main app, but never draws outside the round popup mask.
        bg = QColor(self._ui_bg_color)
        frame = QColor(self._ui_frame_color)
        painter.save()
        painter.setPen(QPen(QColor(frame.red(), frame.green(), frame.blue(), 115), 1))
        painter.setBrush(QColor(bg.red(), bg.green(), bg.blue(), self._ui_alpha))
        painter.drawEllipse(QRectF(rect).adjusted(6, 6, -6, -6))
        painter.restore()

        self._hover_hitboxes = []

        base = 398.0
        scale = min(rect.width(), rect.height()) / base
        origin_x = (rect.width() - base * scale) / 2.0
        origin_y = (rect.height() - base * scale) / 2.0

        painter.save()
        painter.translate(origin_x, origin_y)
        painter.scale(scale, scale)

        # Draw the same zKill fitting-panel transparent assets if they are
        # cached/available. Fallback drawing remains native and transparent.
        if not self._draw_zkb_panel_assets(painter):
            self._draw_fitting_ring(painter, 199, 199, 190, 128)

        if self._loading:
            self._draw_loading_animation(painter)
            painter.restore()
            self._draw_status(painter, rect)
            return

        self._draw_ship_at_zkb_position(painter)
        self._draw_slots_zkb_positions(painter)
        self._draw_kill_summary(painter)
        painter.restore()

        self._draw_status(painter, rect)

    def _draw_loading_animation(self, painter: QPainter):
        painter.save()

        cx = 199.0
        cy = 199.0

        # Big centered loading text with shadow.
        font = QFont(self.font())
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        text_rect = QRectF(78, 174, 242, 36)
        shadow = QColor(0, 0, 0, 190)
        for dx, dy in ((2, 2), (1, 1), (2, 0), (0, 2)):
            painter.setPen(shadow)
            painter.drawText(text_rect.translated(dx, dy), Qt.AlignCenter, "LOADING")
        painter.setPen(QColor(190, 255, 245, 245))
        painter.drawText(text_rect, Qt.AlignCenter, "LOADING")

        # Rotating balls below the text.
        balls = 8
        radius = 34.0
        for i in range(balls):
            angle = self._loading_phase + (math.pi * 2 * i / balls)
            x = cx + math.cos(angle) * radius
            y = cy + 34 + math.sin(angle) * 12
            # Make the leading ball brighter/larger.
            lead = (math.cos(angle - self._loading_phase) + 1.0) / 2.0
            alpha = int(65 + 170 * lead)
            size = 5.0 + 3.0 * lead
            color = QColor(70, 235, 255, alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x - size / 2, y - size / 2, size, size))

        painter.restore()

    def _draw_zkb_panel_assets(self, painter: QPainter) -> bool:
        # Disabled for the circular transparent style: the popup should not use
        # zKill's dark panel background. We keep our own transparent circle
        # outlines and native slot icons instead.
        return False

    def _draw_ship_at_zkb_position(self, painter: QPainter):
        target = QRectF(72, 71, 256, 256)
        painter.save()
        path = QPainterPath()
        path.addEllipse(target.adjusted(5, 5, -5, -5))
        painter.setClipPath(path)
        if not self._ship_pixmap.isNull():
            painter.drawPixmap(target.toRect(), self._ship_pixmap)
        else:
            painter.fillRect(target, QColor(80, 40, 44, 85))
        painter.restore()

    def _draw_icon_at(self, painter: QPainter, x: float, y: float, size: float, type_id: int, border: QColor | None = None, rounded: int = 3, fill_alpha: int = 112) -> QRectF:
        pixmap = self._pixmaps.get(int(type_id)) if type_id else None
        painter.save()
        rect = QRectF(x, y, size, size)
        painter.setPen(QPen(border, 1) if border and border.alpha() > 0 else Qt.NoPen)
        painter.setBrush(QColor(8, 12, 16, min(int(fill_alpha), 60)))
        painter.drawRoundedRect(rect, rounded, rounded)
        if pixmap and not pixmap.isNull():
            inner = rect.adjusted(1.5, 1.5, -1.5, -1.5)
            painter.drawPixmap(inner.toRect(), pixmap)
        painter.restore()
        return rect

    def _draw_fitting_ring(self, painter: QPainter, cx: float, cy: float, outer_r: float, inner_r: float):
        painter.save()
        outer = QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2)
        inner = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)

        # Transparent style: no fills inside the circles, only crisp outlines.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(225, 230, 230, 170), 1.6))
        painter.drawEllipse(outer)
        painter.setPen(QPen(QColor(170, 180, 180, 130), 1.2))
        painter.drawEllipse(inner)

        painter.setPen(QPen(QColor(180, 190, 190, 55), 0.9))
        painter.drawEllipse(QRectF(cx - outer_r * 0.83, cy - outer_r * 0.83, outer_r * 1.66, outer_r * 1.66))
        painter.drawEllipse(QRectF(cx - outer_r * 0.62, cy - outer_r * 0.62, outer_r * 1.24, outer_r * 1.24))
        painter.restore()

    def _draw_ship(self, painter: QPainter, cx: float, cy: float, radius: float):
        target = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        painter.save()
        path = QPainterPath()
        path.addEllipse(target)
        painter.setClipPath(path)
        if not self._ship_pixmap.isNull():
            painter.drawPixmap(target.toRect(), self._ship_pixmap)
        else:
            painter.fillRect(target, QColor(80, 40, 44, 85))
        painter.restore()

        painter.save()
        painter.setPen(QPen(QColor(205, 215, 220, 140), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(target)
        painter.restore()

    def _slot_position_for_index(
        self,
        slot_index: int,
        max_slots: int,
        start_deg: float,
        end_deg: float,
        cx: float,
        cy: float,
        radius: float,
    ):
        """Return a fixed EVE-like slot position.

        zKill/EVE do not compact modules together when a middle slot is empty;
        each flag has a stable location on its rack. Using the slot flag index
        makes the popup visually line up like the fitting panel instead of
        spreading every visible module across a whole semicircle.
        """
        slot_index = max(0, min(int(slot_index or 0), max_slots - 1))
        if max_slots <= 1:
            deg = (start_deg + end_deg) / 2
        else:
            deg = start_deg + ((end_deg - start_deg) * slot_index / (max_slots - 1))
        rad = math.radians(deg)
        return cx + math.cos(rad) * radius, cy + math.sin(rad) * radius, deg

    def _draw_slots_zkb_positions(self, painter: QPainter):
        items = (self._fit_data or {}).get("items") if self._fit_data else {}
        if not isinstance(items, dict):
            items = {}

        # Exact positions copied from zKillboard's 398x398 Fitting_Panel HTML.
        module_pos = {
            "high": [(73, 60), (102, 42), (134, 27), (169, 21), (203, 22), (238, 30), (270, 45), (295, 64)],
            "mid": [(26, 140), (24, 176), (23, 212), (30, 245), (46, 278), (69, 304), (100, 328), (133, 342)],
            "low": [(344, 143), (350, 178), (349, 213), (340, 246), (323, 277), (300, 304), (268, 324), (234, 338)],
            "rig": [(148, 259), (185, 267), (221, 259)],
            "subsystem": [(126, 298), (160, 307), (194, 307), (228, 298)],
        }
        # Ammo/script positions. High charges are intentionally centered
        # directly BELOW their high-slot module, so they never visually mix
        # with the top weapon row.
        charge_pos = {
            "high": [(77, 92), (106, 74), (138, 59), (173, 53), (207, 54), (242, 62), (274, 77), (299, 96)],
            "mid": [(59, 154), (54, 182), (56, 210), (62, 238), (76, 265), (94, 288), (118, 305), (146, 318)],
            "low": [(315, 150), (319, 179), (318, 206), (310, 234), (297, 261), (275, 283), (251, 300), (225, 310)],
        }

        border = {
            "high": QColor(246, 185, 66, 230),
            "mid": QColor(90, 198, 255, 230),
            "low": QColor(255, 145, 72, 230),
            "rig": QColor(115, 245, 165, 230),
            "subsystem": QColor(180, 145, 255, 220),
        }

        # Draw ammo/scripts first so the weapon/module remains visually primary.
        # High-slot ammo is smaller and lower than the module row.
        for slot in ("high", "mid", "low"):
            slot_items = list(items.get(slot) or [])
            for row in slot_items:
                slot_index = max(0, min(_safe_int(row.get("slot_index")), len(charge_pos[slot]) - 1))
                charge_type_id = _safe_int(row.get("charge_type_id"))
                if not charge_type_id:
                    continue
                cx, cy = charge_pos[slot][slot_index]
                charge_size = 20 if slot == "high" else 24
                rect = self._draw_icon_at(
                    painter,
                    cx,
                    cy,
                    charge_size,
                    charge_type_id,
                    QColor(230, 230, 230, 145),
                    rounded=2,
                    fill_alpha=70,
                )
                self._hover_hitboxes.append((rect, self._type_name(charge_type_id)))

        # Draw only populated slots. Empty slots are intentionally hidden.
        for slot in ("high", "mid", "low", "rig", "subsystem"):
            slot_items = list(items.get(slot) or [])
            if not slot_items:
                continue
            max_idx = len(module_pos[slot]) - 1
            for row in slot_items:
                slot_index = max(0, min(_safe_int(row.get("slot_index")), max_idx))
                x, y = module_pos[slot][slot_index]
                type_id = _safe_int(row.get("type_id"))
                rect = self._draw_icon_at(painter, x, y, 32, type_id, border[slot])
                self._hover_hitboxes.append((rect, self._type_name(type_id)))

    def _draw_item_box_center(
        self,
        painter: QPainter,
        x: float,
        y: float,
        size: float,
        type_id: int,
        border: QColor,
        angle: float = 0.0,
        filled: bool = True,
        radius: int = 3,
    ):
        painter.save()
        painter.translate(x, y)
        painter.rotate(angle)
        rect = QRectF(-size / 2, -size / 2, size, size)
        painter.setPen(QPen(border, 1))
        painter.setBrush(QColor(7, 12, 14, 118 if filled else 38))
        painter.drawRoundedRect(rect, radius, radius)
        pixmap = self._pixmaps.get(int(type_id)) if type_id else None
        if pixmap and not pixmap.isNull():
            inner = rect.adjusted(2.5, 2.5, -2.5, -2.5)
            painter.drawPixmap(inner.toRect(), pixmap)
        painter.restore()

    def _draw_item_box(self, painter: QPainter, rect: QRectF, type_id: int, border: QColor, radius: int = 3):
        # Kept for compatibility with older cached paths; new layout uses
        # _draw_item_box_center() so slot boxes can follow the ring angle.
        painter.save()
        painter.setPen(QPen(border, 1))
        painter.setBrush(QColor(8, 13, 15, 105))
        painter.drawRoundedRect(rect, radius, radius)
        pixmap = self._pixmaps.get(int(type_id)) if type_id else None
        if pixmap and not pixmap.isNull():
            inner = rect.adjusted(2, 2, -2, -2)
            painter.drawPixmap(inner.toRect(), pixmap)
        painter.restore()

    def _draw_kill_summary(self, painter: QPainter):
        if not isinstance(self._fit_data, dict):
            return

        damage = _safe_int(self._fit_data.get("damage_taken"), 0)
        destroyed = self._fit_data.get("destroyed_value", 0)
        dropped = self._fit_data.get("dropped_value", 0)
        total = self._fit_data.get("total_value", 0)

        ship_name = str(self._fit_data.get("ship_name") or self._row_data.get("ship_name") or "Ship")
        location_name = str(self._row_data.get("location_name") or self._row_data.get("location") or "-")
        rows = [
            (f"Ship: {ship_name}", QColor("#ffffff")),
            (f"Location: {location_name}", QColor("#ffffff")),
            (f"Damage: {damage:,}".replace(",", " ") if damage > 0 else "Damage: -", QColor("#ffffff")),
            (f"Destroyed: {_format_isk_short(destroyed)}", QColor("#ff3333")),
            (f"Dropped: {_format_isk_short(dropped)}", QColor("#45d66f")),
            (f"Total: {_format_isk_short(total)}", QColor("#22cc44")),
        ]

        painter.save()
        font = QFont(self.font())
        font.setPointSize(8)
        font.setBold(True)
        shadow = QColor(0, 0, 0, 190)

        start_y = 122
        row_h = 16
        full_w = 220
        x0 = 199 - full_w / 2

        def draw_center_line(rect, text, color):
            painter.setFont(font)
            painter.setPen(shadow)
            for dx, dy in ((1, 1), (1, 0), (0, 1)):
                painter.drawText(rect.translated(dx, dy), Qt.AlignHCenter | Qt.AlignVCenter, text)
            painter.setPen(color)
            painter.drawText(rect, Qt.AlignHCenter | Qt.AlignVCenter, text)

        for idx, (line_text, color) in enumerate(rows):
            y = start_y + idx * row_h
            draw_center_line(QRectF(x0, y, full_w, row_h), line_text, color)

        if self._hovered_module_name:
            hover_font = QFont(font)
            hover_font.setPointSize(8)
            hover_font.setBold(True)
            painter.setFont(hover_font)
            hover_rect = QRectF(54, start_y + len(rows) * row_h + 2, 290, 22)
            painter.setPen(shadow)
            for dx, dy in ((1, 1), (1, 0), (0, 1)):
                painter.drawText(hover_rect.translated(dx, dy), Qt.AlignHCenter | Qt.AlignVCenter, self._hovered_module_name)
            painter.setPen(QColor(210, 245, 255, 245))
            painter.drawText(hover_rect, Qt.AlignHCenter | Qt.AlignVCenter, self._hovered_module_name)

        painter.restore()

    def _draw_status(self, painter: QPainter, rect):
        text = ""
        if self._loading:
            text = ""
        elif self._error:
            text = "Fit unavailable"
        elif self._fit_data:
            text = ""

        if not text:
            return

        painter.save()
        font = QFont(self.font())
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(170, 255, 235, 225) if not self._error else QColor(255, 165, 165, 225))
        painter.drawText(rect.adjusted(8, 4, -8, -8), Qt.AlignTop | Qt.AlignHCenter, text)
        if self._error:
            font.setBold(False)
            font.setPointSize(8)
            painter.setFont(font)
            painter.setPen(QColor(220, 205, 205, 180))
            painter.drawText(rect.adjusted(24, 24, -24, -8), Qt.AlignTop | Qt.AlignHCenter | Qt.TextWordWrap, self._error[:140])
        painter.restore()
