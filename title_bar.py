from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QRadialGradient
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from app_fonts import APP_FONT_FAMILY


class TitleIconButton(QPushButton):
    def __init__(self, icon_type, parent=None):
        super().__init__(parent)
        self.icon_type = icon_type

        self.frame_color = QColor("#3D424A")
        self.text_color = QColor("#AEB4BC")
        self.tint_color = QColor("#7CFFF0")
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
            QPushButton:checked {
                border: none;
                background: transparent;
            }
        """)

    def set_colors(self, frame_color, text_color, tint_color="#7CFFF0"):
        self.frame_color = QColor(frame_color)
        self.text_color = QColor(text_color)
        self.tint_color = QColor(tint_color)
        self.update()

    def _draw_glow(self, painter: QPainter, color: QColor, radius: int = 8):
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

        is_hover = self.underMouse()
        is_checked = self.isCheckable() and self.isChecked()

        if self.icon_type == "close" and is_hover:
            icon = QColor(self.close_hover_color)
            self._draw_glow(painter, icon, 9)
        elif is_checked:
            icon = QColor(self.tint_color)
            self._draw_glow(painter, icon, 9)
        elif is_hover:
            icon = QColor(self.hover_color)
            self._draw_glow(painter, icon, 8)
        else:
            icon = QColor(self.text_color)
            icon.setAlpha(210)

        cx = self.width() / 2
        cy = self.height() / 2

        painter.setPen(QPen(icon, 1.35, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(icon)

        center = QPointF(cx, cy)

        if self.icon_type == "pin":
            # Small EVE-like status dot. Use floating point drawing so it stays
            # visually centered; int QRect drawing shifts tiny icons up-left.
            radius = 1.9 if not is_checked else 2.2
            painter.drawEllipse(center, radius, radius)
        elif self.icon_type == "minimize":
            painter.drawLine(QPointF(cx - 4.0, cy), QPointF(cx + 4.0, cy))
        elif self.icon_type == "close":
            size = 4.0
            painter.drawLine(QPointF(cx - size, cy - size), QPointF(cx + size, cy + size))
            painter.drawLine(QPointF(cx + size, cy - size), QPointF(cx - size, cy + size))

        painter.end()


class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        self.parent_window = parent

        self.setObjectName("TitleBar")
        self.setFixedHeight(24)

        self.frame_color = "#3D424A"
        self.text_color = "#D6D8DC"
        self.font_size = 8
        self.title_alpha = 248
        self.tint_color = "#7CFFF0"
        self.tabs_widget = None

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(5, 1, 5, 1)
        self.layout.setSpacing(0)

        # The old text title took vertical space and duplicated the tabs.
        # Keep the QLabel only for compatibility, but do not show it.
        self.title = QLabel("")
        self.title.hide()
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.top_button = TitleIconButton("pin", self)
        self.top_button.setCheckable(True)

        self.minimize_button = TitleIconButton("minimize", self)
        self.close_button = TitleIconButton("close", self)

        self.top_button.toggled.connect(self.parent_window.toggle_always_on_top)
        self.minimize_button.clicked.connect(self.parent_window.showMinimized)
        self.close_button.clicked.connect(self.parent_window.close)

        self.layout.addStretch()
        self.layout.addWidget(self.top_button)
        self.layout.addWidget(self.minimize_button)
        self.layout.addWidget(self.close_button)

        self.setLayout(self.layout)
        self.apply_style(self.frame_color, self.text_color, self.font_size, self.title_alpha)

    def set_tabs_widget(self, tabs_widget):
        """Put General/Zkill/Options into the title bar instead of a second row."""
        if self.tabs_widget is not None:
            self.tabs_widget.setParent(None)

        self.tabs_widget = tabs_widget
        self.tabs_widget.setParent(self)
        self.tabs_widget.setFixedHeight(22)

        # Insert before the stretch, so window buttons stay at the right side.
        self.layout.insertWidget(0, self.tabs_widget, 0, Qt.AlignLeft | Qt.AlignVCenter)

    def apply_style(self, frame_color="#3D424A", text_color="#D6D8DC", font_size=8, title_alpha=248):
        self.frame_color = frame_color
        self.text_color = text_color
        self.font_size = font_size
        self.title_alpha = title_alpha

        self.title.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-family: '{APP_FONT_FAMILY}'; font-size: {font_size}pt;
                font-weight: normal;
                background-color: transparent;
            }}
        """)

        for button in (self.top_button, self.minimize_button, self.close_button):
            button.set_colors(frame_color, text_color, self.tint_color)

        # No text title here; tabs live inside this bar.
        self.setStyleSheet(f"""
            QWidget#TitleBar {{
                background-color: rgba(12, 13, 15, {int(title_alpha)});
                border: none;
                border-bottom: 1px solid {frame_color};
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.position().toPoint())
            if isinstance(child, QPushButton):
                return super().mousePressEvent(event)

            # Do not hijack clicks from the embedded tab widget.
            if self.tabs_widget is not None:
                current = child
                while current is not None:
                    if current is self.tabs_widget:
                        return super().mousePressEvent(event)
                    current = current.parentWidget() if hasattr(current, "parentWidget") else None

            window = self.parent_window.windowHandle()
            if window:
                window.startSystemMove()
            event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()
