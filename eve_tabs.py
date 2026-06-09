from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel


class EveTabs(QWidget):
    tabChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.buttons = {}
        self._drag_active = False
        self._drag_offset = QPoint()

        self.setObjectName("EveTabs")
        self.setFixedHeight(22)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 0, 4, 0)
        self.layout.setSpacing(3)

        for tab_name in ["General", "Zkill", "Options"]:
            button = QPushButton(tab_name)
            button.setCheckable(True)
            button.setFixedHeight(18)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, name=tab_name: self.set_active(name)
            )

            self.buttons[tab_name] = button
            self.layout.addWidget(button)

        self.layout.addStretch()

        self.linked_label = QLabel("")
        self.linked_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.layout.addWidget(self.linked_label)

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

        self.tabChanged.emit(name)

    def set_linked_count(self, count):
        if count > 0:
            self.linked_label.setText(f"linked pilots: {count}")
        else:
            self.linked_label.setText("")

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

        for button in self.buttons.values():
            font = button.font()
            font.setPointSize(font_size)
            button.setFont(font)

        label_font = self.linked_label.font()
        label_font.setPointSize(font_size)
        self.linked_label.setFont(label_font)

        self.setStyleSheet(f"""
            QWidget#EveTabs {{
                background-color: transparent;
                border-top: 1px solid {frame_color};
                border-left: 1px solid {frame_color};
                border-right: 1px solid #07080A;
                border-bottom: 1px solid #07080A;
            }}

            QPushButton {{
                background-color: rgba(14, 16, 20, 120);
                color: {text_color};
                border: 1px solid transparent;
                padding: 0px 8px;
                font-size: {font_size}pt;
            }}

            QPushButton:hover {{
                background-color: rgba(40, 45, 52, 180);
                border: 1px solid {frame_color};
                color: #FFFFFF;
            }}

            QPushButton:checked {{
                background-color: rgba(18, 24, 26, 210);
                color: #A9F5E0;
                border-bottom: 1px solid #39C7B5;
            }}

            QLabel {{
                color: #8F959C;
                font-size: {font_size}pt;
                background: transparent;
            }}
        """)
