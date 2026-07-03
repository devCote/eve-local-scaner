"""Native transparent zKill fitting popup.

This popup does NOT embed a browser and does NOT render zKillboard HTML.
It uses API data to build a local EVE-style circular fit view inside Qt.
"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRegion, QBrush, QRadialGradient
from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from user_settings import load_ui_settings
from windows_blur import enable_eve_blur
from app_fonts import get_app_font_family
from zkill_fit_export import build_eft_fit_text
from zkill_fit_fetcher import NativeFitFetchThread
from zkill_fit_utils import format_isk_short, safe_int, transparency_to_alpha


class PopupCloseButton(QPushButton):
    """Small drawn close button matching the app title-bar close icon."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_color = QColor("#AEB4BC")
        self.hover_color = QColor("#E6EEF6")
        self.close_hover_color = QColor("#FF8A8A")

        self.setFixedSize(20, 16)
        self.setCursor(Qt.PointingHandCursor)
        self.setText("")
        self.setFlat(True)
        self.setMouseTracking(True)
        self.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                border: none;
                background: transparent;
            }
            QPushButton:pressed {
                border: none;
                background: transparent;
            }
        """)

    def set_colors(self, text_color: str):
        color = QColor(text_color)
        if color.isValid():
            self.text_color = color
        self.update()

    def _draw_glow(self, painter: QPainter, color: QColor, radius: int = 9):
        cx = self.width() / 2
        cy = self.height() / 2

        glow = QRadialGradient(cx, cy, radius)
        c1 = QColor(color)
        c1.setAlpha(90)
        c2 = QColor(color)
        c2.setAlpha(0)
        glow.setColorAt(0.0, c1)
        glow.setColorAt(1.0, c2)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(int(cx - radius), int(cy - radius), radius * 2, radius * 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self.underMouse():
            icon = QColor(self.close_hover_color)
            self._draw_glow(painter, icon, 9)
        else:
            icon = QColor(self.text_color)
            icon.setAlpha(215)

        cx = self.width() / 2
        cy = self.height() / 2
        size = 4.0

        painter.setPen(QPen(icon, 1.35, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(QPointF(cx - size, cy - size), QPointF(cx + size, cy + size))
        painter.drawLine(QPointF(cx + size, cy - size), QPointF(cx - size, cy + size))
        painter.end()


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
        self._loading_timer.setInterval(110)
        self._loading_timer.timeout.connect(self._advance_loading_animation)
        self._owner_widget = None

        # Visual settings copied from the main app at show time.
        settings = load_ui_settings()
        self._ui_transparency = int(settings.get("transparency", 10))
        self._ui_alpha = transparency_to_alpha(self._ui_transparency)
        self._ui_blur = int(settings.get("blur", 0))
        self._ui_bg_color = str(settings.get("bg_color", "#0b0b0b"))
        self._ui_frame_color = str(settings.get("frame_color", "#161616"))
        self._ui_text_color = str(settings.get("text_color", "#d6d6d6"))

        self.setFixedSize(398, 398)
        self._apply_circle_mask()

        self.save_fit_button = QPushButton("Save Fit", self)
        self.save_fit_button.setCursor(Qt.PointingHandCursor)
        self.save_fit_button.clicked.connect(self._copy_fit_to_clipboard)
        self.save_fit_button.installEventFilter(self)
        self._apply_save_fit_button_style()
        self.save_fit_button.hide()

        self.close_button = PopupCloseButton(self)
        self.close_button.clicked.connect(self._close_popup)
        self.close_button.installEventFilter(self)
        self._apply_close_button_style()
        self.close_button.show()

    def _apply_save_fit_button_style(self):
        frame = QColor(self._ui_frame_color)
        if not frame.isValid():
            frame = QColor("#3D424A")

        text = QColor(self._ui_text_color)
        if not text.isValid():
            text = QColor("#d6d6d6")

        bg = QColor(self._ui_bg_color)
        if not bg.isValid():
            bg = QColor("#0b0b0b")

        r, g, b = frame.red(), frame.green(), frame.blue()
        tr, tg, tb = text.red(), text.green(), text.blue()
        br, bg_g, bb = bg.red(), bg.green(), bg.blue()

        # Default button background uses the current global Background color.
        # Hover is the same color, only slightly brighter.
        hover_r = min(255, int(br * 1.22) + 10)
        hover_g = min(255, int(bg_g * 1.22) + 10)
        hover_b = min(255, int(bb * 1.22) + 10)
        pressed_r = min(255, int(br * 1.35) + 14)
        pressed_g = min(255, int(bg_g * 1.35) + 14)
        pressed_b = min(255, int(bb * 1.35) + 14)

        self.save_fit_button.setStyleSheet(
            "QPushButton {"
            f"background-color: rgba({br}, {bg_g}, {bb}, 210);"
            f"color: rgba({tr}, {tg}, {tb}, 245);"
            f"border: 1px solid rgba({r}, {g}, {b}, 190);"
            f"border-radius: 5px; padding: 1px 10px; font-family: '{get_app_font_family()}'; font-size: 10px; font-weight: 600;"
            "}"
            "QPushButton:hover {"
            f"background-color: rgba({hover_r}, {hover_g}, {hover_b}, 225);"
            f"border: 1px solid rgba({r}, {g}, {b}, 235);"
            f"color: rgba({tr}, {tg}, {tb}, 255);"
            "}"
            "QPushButton:pressed {"
            f"background-color: rgba({pressed_r}, {pressed_g}, {pressed_b}, 235);"
            "}"
        )

    def _apply_close_button_style(self):
        self.close_button.set_colors(self._ui_text_color)

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
        # Keep the close icon inside the circular mask, near the right-top
        # area like the main window close button.
        self.close_button.setGeometry(max(0, self.width() - 86), 62, 20, 16)
        self.close_button.raise_()

    def _copy_fit_to_clipboard(self):
        fit_data = self._fit_data if isinstance(self._fit_data, dict) else {}
        row_data = self._row_data if isinstance(self._row_data, dict) else {}
        text = build_eft_fit_text(fit_data, row_data)
        QApplication.clipboard().setText(text)

    def _type_name(self, type_id: int) -> str:
        fit_data = self._fit_data if isinstance(self._fit_data, dict) else {}
        type_names = fit_data.get("type_names") if isinstance(fit_data.get("type_names"), dict) else {}
        return str(type_names.get(int(type_id), f"Type {int(type_id)}"))

    def show_for_row(self, row_data: dict, owner_widget, pinned: bool = False):
        killmail_id = safe_int((row_data or {}).get("killmail_id"))
        if not killmail_id:
            self.hide()
            return

        self._row_data = dict(row_data or {})
        self._owner_widget = owner_widget
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
        self._apply_save_fit_button_style()
        self._apply_close_button_style()
        self._apply_circle_mask()
        self._layout_button()
        self._move_near_owner(owner_widget)
        self.show()
        QTimer.singleShot(0, self._apply_window_blur)
        QTimer.singleShot(80, self._apply_window_blur)
        self.save_fit_button.hide()
        self.close_button.show()
        self.close_button.raise_()
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
        text_color = getattr(window, "ui_text_color", None)

        if transparency is None or alpha is None:
            settings = load_ui_settings()
            transparency = settings.get("transparency", self._ui_transparency)
            alpha = transparency_to_alpha(int(transparency))
            blur = settings.get("blur", self._ui_blur)
            bg_color = settings.get("bg_color", self._ui_bg_color)
            frame_color = settings.get("frame_color", self._ui_frame_color)
            text_color = settings.get("text_color", self._ui_text_color)

        self._ui_transparency = max(0, min(100, int(transparency)))
        self._ui_alpha = max(0, min(255, int(alpha)))
        self._ui_blur = 1 if int(blur or 0) else 0
        self._ui_bg_color = str(bg_color or "#0b0b0b")
        self._ui_frame_color = str(frame_color or "#161616")
        self._ui_text_color = str(text_color or "#d6d6d6")

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
        self._owner_widget = None

    def _close_popup(self):
        self.hide_panel(force=True)
        self.mouseLeft.emit()

    def enterEvent(self, event):
        self._mouse_inside = True
        super().enterEvent(event)

    def _close_on_right_middle_event(self, event) -> bool:
        if event.type() == QEvent.MouseButtonPress and event.button() in (Qt.RightButton, Qt.MiddleButton):
            self._close_popup()
            event.accept()
            return True
        return False

    def eventFilter(self, obj, event):
        if self._close_on_right_middle_event(event):
            return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if self._close_on_right_middle_event(event):
            return
        super().mousePressEvent(event)

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
        if self._hovered_module_name:
            self._hovered_module_name = ""
            self.update()
        # Do not close the pinned fit popup when the mouse leaves it.
        # It now closes only by:
        #   - the top-right x button;
        #   - right click inside the popup;
        #   - middle click inside the popup;
        #   - explicit close from parent/tab/window logic.
        super().leaveEvent(event)

    def follow_owner_position(self):
        """Move visible popup together with the main window."""
        if not self.isVisible():
            return
        owner_widget = self._owner_widget
        if owner_widget is None:
            return
        try:
            self._move_near_owner(owner_widget)
        except RuntimeError:
            # Owner widget was destroyed.
            self._owner_widget = None

    def _move_near_owner(self, owner_widget):
        """Place popup around the main app window.

        Horizontal:
          - main on left half of screen  -> popup opens to the right
          - main on right half of screen -> popup opens to the left

        Vertical:
          - main on top half of screen    -> popup top aligns with main top
          - main on bottom half of screen -> popup bottom aligns with main bottom
        """
        window = owner_widget.window() if owner_widget else None
        app = QApplication.instance()

        if not window:
            active = app.activeWindow() if app else None
            if active:
                window = active

        if not window:
            self.move(QPoint(20, 20))
            return

        geo = window.frameGeometry()
        screen = QApplication.screenAt(geo.center()) or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        gap = 8

        if available:
            screen_center_x = available.left() + available.width() / 2.0
            screen_center_y = available.top() + available.height() / 2.0
        else:
            screen_center_x = geo.center().x()
            screen_center_y = geo.center().y()

        # Choose side by main window position on screen.
        if geo.center().x() <= screen_center_x:
            x = geo.right() + gap
        else:
            x = geo.left() - self.width() - gap

        # Align to top or bottom of main window.
        if geo.center().y() <= screen_center_y:
            y = geo.top()
        else:
            y = geo.bottom() - self.height() + 1

        if available:
            # If chosen side is out of screen, flip to the opposite side.
            if x + self.width() > available.right():
                x = geo.left() - self.width() - gap
            elif x < available.left():
                x = geo.right() + gap

            # Clamp as a final safety for very small screens/windows.
            x = max(available.left(), min(x, available.right() - self.width() + 1))
            y = max(available.top(), min(y, available.bottom() - self.height() + 1))

        self.move(QPoint(int(x), int(y)))

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

    def _frame_color(self, alpha: int = 230) -> QColor:
        color = QColor(self._ui_frame_color)
        if not color.isValid():
            color = QColor("#3D424A")
        color.setAlpha(max(0, min(255, int(alpha))))
        return color

    def _frame_pen(self, alpha: int = 230, width: float = 1.0) -> QPen:
        return QPen(self._frame_color(alpha), width)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = self.rect().adjusted(0, 0, 0, 0)

        # Circular popup background uses the same transparency/bg/frame settings
        # as the main app, but never draws outside the round popup mask.
        bg = QColor(self._ui_bg_color)
        painter.save()
        painter.setPen(self._frame_pen(115, 1))
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
            # Darken the ship image by ~30% for better text readability.
            painter.fillPath(path, QColor(0, 0, 0, 76))
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

        # All popup orbit/circle outlines follow global Options -> Frame color.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(self._frame_pen(205, 1.6))
        painter.drawEllipse(outer)
        painter.setPen(self._frame_pen(165, 1.2))
        painter.drawEllipse(inner)

        painter.setPen(self._frame_pen(85, 0.9))
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
        painter.setPen(self._frame_pen(165, 2))
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
                slot_index = max(0, min(safe_int(row.get("slot_index")), len(charge_pos[slot]) - 1))
                charge_type_id = safe_int(row.get("charge_type_id"))
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
                slot_index = max(0, min(safe_int(row.get("slot_index")), max_idx))
                x, y = module_pos[slot][slot_index]
                type_id = safe_int(row.get("type_id"))
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

        damage = safe_int(self._fit_data.get("damage_taken"), 0)
        destroyed = self._fit_data.get("destroyed_value", 0)
        dropped = self._fit_data.get("dropped_value", 0)
        total = self._fit_data.get("total_value", 0)

        ship_name = str(self._fit_data.get("ship_name") or self._row_data.get("ship_name") or "Ship")
        location_name = str(self._row_data.get("location_name") or self._row_data.get("location") or "-")
        rows = [
            (f"Ship: {ship_name}", QColor("#ffffff")),
            (f"Location: {location_name}", QColor("#ffffff")),
            (f"Damage: {damage:,}".replace(",", " ") if damage > 0 else "Damage: -", QColor("#ffffff")),
            (f"Destroyed: {format_isk_short(destroyed)}", QColor("#ff3333")),
            (f"Dropped: {format_isk_short(dropped)}", QColor("#45d66f")),
            (f"Total: {format_isk_short(total)}", QColor("#22cc44")),
        ]

        painter.save()
        font = QFont(self.font())
        font.setPointSize(9)
        font.setBold(True)
        shadow = QColor(0, 0, 0, 190)

        start_y = 120
        row_h = 17
        full_w = 240
        x0 = 199 - full_w / 2

        def draw_center_line(rect, text, color):
            painter.setFont(font)

            # Readability layer: small rounded background only under the text,
            # not a full-width panel. It follows real text width + padding.
            metrics = painter.fontMetrics()
            text_w = min(rect.width() - 6, metrics.horizontalAdvance(text) + 14)
            bg_rect = QRectF(
                rect.center().x() - text_w / 2,
                rect.y() + 1,
                text_w,
                rect.height() - 2,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 118))
            painter.drawRoundedRect(bg_rect, 4, 4)

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
            hover_font.setPointSize(9)
            hover_font.setBold(True)
            painter.setFont(hover_font)
            hover_rect = QRectF(54, start_y + len(rows) * row_h + 2, 290, 22)
            metrics = painter.fontMetrics()
            hover_w = min(hover_rect.width() - 8, metrics.horizontalAdvance(self._hovered_module_name) + 16)
            hover_bg = QRectF(
                hover_rect.center().x() - hover_w / 2,
                hover_rect.y() + 2,
                hover_w,
                hover_rect.height() - 4,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 125))
            painter.drawRoundedRect(hover_bg, 4, 4)

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
