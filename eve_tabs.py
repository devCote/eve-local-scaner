from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSizePolicy

from app_fonts import APP_FONT_FAMILY


class EveTabs(QWidget):
    tabChanged = Signal(str)
    zkillModeChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.buttons = {}
        self._drag_active = False
        self._drag_offset = QPoint()
        self._compact_labels = False
        self._main_labels = {
            "General": ("General", "Gen"),
            "Zkill": ("Zkill", "Zkb"),
            "Options": ("Options", "Opt"),
        }
        self._mode_labels = {
            "All": ("All", "All"),
            "Kill": ("Kill", "Kil"),
            "Loss": ("Loss", "Los"),
        }
        self._last_bg_color = "#0b0b0b"
        self._last_frame_color = "#2F343B"
        self._last_text_color = "#C7C9CC"
        self._last_font_size = 10

        self.setObjectName("EveTabs")
        self.setFixedHeight(22)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        for tab_name in ["General", "Zkill", "Options"]:
            button = QPushButton(tab_name)
            button.setObjectName("MainTabButton")
            button.setCheckable(True)
            button.setFixedHeight(20)
            button.setMinimumWidth(22)
            button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, name=tab_name: self.set_active(name)
            )

            self.buttons[tab_name] = button
            self.layout.addWidget(button)

        self.zkill_mode_buttons = {}
        for mode_name, label in [("All", "All"), ("Kill", "Kill"), ("Loss", "Loss")]:
            button = QPushButton(label)
            button.setObjectName("ZkillModeButton")
            button.setCheckable(True)
            button.setFixedHeight(20)
            button.setMinimumWidth(20)
            button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, name=mode_name: self.set_zkill_mode(name, emit=True)
            )
            self.zkill_mode_buttons[mode_name] = button
            self.layout.addWidget(button)

        self.layout.addStretch()

        self.set_zkill_modes_visible(False)
        self.set_zkill_mode("All", emit=False)
        self.set_active("General")

        self.apply_colors("#2F343B", "#C7C9CC")


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.position().toPoint())

            # Do not drag when clicking real tab buttons.
            if isinstance(child, QPushButton):
                super().mousePressEvent(event)
                return

            window = self.window()
            if window:
                self._drag_active = True
                self._drag_offset = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active and event.buttons() & Qt.LeftButton:
            window = self.window()
            if window:
                window.move(event.globalPosition().toPoint() - self._drag_offset)
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_active = False
        super().mouseReleaseEvent(event)

    def set_active(self, name):
        for tab_name, button in self.buttons.items():
            button.setChecked(tab_name == name)

        self.set_zkill_modes_visible(name == "Zkill")
        self.tabChanged.emit(name)

    def set_zkill_modes_visible(self, visible: bool):
        for button in getattr(self, "zkill_mode_buttons", {}).values():
            button.setVisible(bool(visible))

    def set_zkill_mode(self, name: str, emit: bool = True):
        if name not in getattr(self, "zkill_mode_buttons", {}):
            name = "All"

        for mode_name, button in self.zkill_mode_buttons.items():
            button.setChecked(mode_name == name)

        if emit:
            self.set_active("Zkill")
            self.zkillModeChanged.emit(name)

    def set_linked_count(self, count):
        # Status text is intentionally hidden from the tab bar.
        # Keep this method as a no-op so existing callers in ui.py stay compatible.
        return

    def _apply_compact_labels(self, compact: bool, force: bool = False):
        compact = bool(compact)
        if not force and compact == self._compact_labels:
            return
        self._compact_labels = compact

        for name, button in self.buttons.items():
            long_label, short_label = self._main_labels.get(name, (name, name[:3]))
            button.setText(short_label if compact else long_label)

        for name, button in self.zkill_mode_buttons.items():
            long_label, short_label = self._mode_labels.get(name, (name, name[:3]))
            button.setText(short_label if compact else long_label)

        # Update padding too; otherwise short text can still reserve too much width.
        self.apply_colors(self._last_bg_color, self._last_frame_color, self._last_text_color, self._last_font_size)

    def update_compact_labels_for_width(self, width: int | None = None, force: bool = False):
        """Switch labels by the whole app window width, not tab widget width."""
        if width is None:
            window = self.window()
            width = window.width() if window is not None else self.width()
        self._apply_compact_labels(int(width) < 300, force=force)

    def _update_compact_labels(self):
        self.update_compact_labels_for_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_compact_labels()

    def apply_colors(self, *args):
        """Apply tab colors and use the global UI font size.

        Supported calls:
            apply_colors(frame_color, text_color)
            apply_colors(bg_color, frame_color, text_color)
            apply_colors(bg_color, frame_color, text_color, font_size)

        Also tolerates the old mistaken order:
            apply_colors(frame_color, text_color, font_size, bg_color)
        """
        bg_color = "#0b0b0b"
        frame_color = "#2F343B"
        text_color = "#C7C9CC"
        font_size = 10

        if len(args) == 1:
            frame_color = args[0]

        elif len(args) == 2:
            frame_color, text_color = args

        elif len(args) == 3:
            bg_color, frame_color, text_color = args

        elif len(args) >= 4:
            a, b, c, d = args[:4]

            # Correct order: bg, frame, text, font
            if isinstance(d, int) or str(d).isdigit():
                bg_color, frame_color, text_color, font_size = a, b, c, d

            # Old wrong order: frame, text, font, bg
            elif isinstance(c, int) or str(c).isdigit():
                frame_color, text_color, font_size, bg_color = a, b, c, d

            else:
                bg_color, frame_color, text_color, font_size = a, b, c, d

        try:
            font_size = int(font_size)
        except Exception:
            font_size = 10

        font_size = max(7, min(18, font_size))
        self._last_bg_color = bg_color
        self._last_frame_color = frame_color
        self._last_text_color = text_color
        self._last_font_size = font_size

        main_pad = 4 if getattr(self, "_compact_labels", False) else 8
        mode_pad = 4 if getattr(self, "_compact_labels", False) else 7

        for button in list(self.buttons.values()) + list(getattr(self, "zkill_mode_buttons", {}).values()):
            font = button.font()
            font.setFamily(APP_FONT_FAMILY)
            font.setPointSize(font_size)
            button.setFont(font)

        self.setStyleSheet(f"""
            QWidget#EveTabs {{
                background-color: transparent;
                border: none;
            }}

            QPushButton#MainTabButton {{
                background-color: rgba(14, 16, 20, 120);
                color: {text_color};
                border: 1px solid transparent;
                padding: 0px {main_pad}px;
                font-family: '{APP_FONT_FAMILY}'; font-size: {font_size}pt;
            }}

            QPushButton#MainTabButton:hover {{
                background-color: rgba(40, 45, 52, 180);
                border: 1px solid {frame_color};
                color: #FFFFFF;
            }}

            QPushButton#MainTabButton:checked {{
                background-color: rgba(18, 24, 26, 210);
                color: #A9F5E0;
                border-bottom: 1px solid #39C7B5;
            }}

            QPushButton#ZkillModeButton {{
                background-color: transparent;
                color: {text_color};
                border: 0px;
                padding: 0px {mode_pad}px;
                margin-left: 1px;
                font-family: '{APP_FONT_FAMILY}'; font-size: {font_size}pt;
            }}

            QPushButton#ZkillModeButton:hover {{
                background-color: transparent;
                color: #FFFFFF;
                border: 0px;
            }}

            QPushButton#ZkillModeButton:checked {{
                background-color: transparent;
                color: #A9F5E0;
                border: 0px;
                font-weight: normal;
            }}

        """)
