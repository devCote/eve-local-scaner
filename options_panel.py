from PySide6.QtCore import Qt, Signal, QPoint, QRect, QSize, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QColorDialog,
    QFrame,
    QCheckBox,
    QScrollArea,
    QLayout,
    QSizePolicy,
)

from user_settings import DEFAULT_UI_SETTINGS


class FlowLayout(QLayout):
    """Small wrapping layout for option buttons.

    Qt has no built-in flow/wrap layout for normal widgets. This keeps the
    Options page clean when the user makes the window very narrow: buttons go
    to the next line instead of overlapping/stacking on top of each other.
    """

    def __init__(self, parent=None, margin=0, hspacing=8, vspacing=6):
        super().__init__(parent)
        self._items = []
        self._hspacing = int(hspacing)
        self._vspacing = int(vspacing)
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())

        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def _do_layout(self, rect, test_only=False):
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)

        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue

            item_size = item.sizeHint()
            next_x = x + item_size.width() + self._hspacing

            if x > effective.x() and next_x - self._hspacing > effective.right() + 1:
                x = effective.x()
                y = y + line_height + self._vspacing
                next_x = x + item_size.width() + self._hspacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + bottom


class OptionsPanel(QWidget):
    # transparency, blur, font_size, frame_color, text_color, bg_color
    settingsChanged = Signal(int, int, int, str, str, str)
    clearDataRequested = Signal()
    healthCheckRequested = Signal()
    generalTableRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.transparency = DEFAULT_UI_SETTINGS["transparency"]
        self.blur = DEFAULT_UI_SETTINGS["blur"]
        self.font_size = DEFAULT_UI_SETTINGS["font_size"]
        self.frame_color = DEFAULT_UI_SETTINGS["frame_color"]
        self.text_color = DEFAULT_UI_SETTINGS["text_color"]
        self.bg_color = DEFAULT_UI_SETTINGS["bg_color"]

        self._loading_values = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setAttribute(Qt.WA_StyledBackground, True)
        self.scroll_area.viewport().setAutoFillBackground(False)

        self.content = QWidget()
        self.content.setObjectName("OptionsContent")
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.scroll_area.setWidget(self.content)
        root_layout.addWidget(self.scroll_area, 1)

        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        # Keep the scroll area's internal widget sized from its real content.
        # Without this, Qt can temporarily give the wrapped buttons a wrong
        # height on startup; the Options controls then appear collapsed until
        # the user manually resizes the window.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)

        self.transparency_label = QLabel()
        self.transparency_label.setObjectName("OptionSliderLabel")
        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setObjectName("CyanOptionSlider")
        self.transparency_slider.setRange(0, 100)
        self.transparency_slider.setValue(self.transparency)
        self.transparency_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.transparency_slider.valueChanged.connect(self.on_transparency_changed)

        self.transparency_row = QHBoxLayout()
        self.transparency_row.setContentsMargins(0, 0, 0, 0)
        self.transparency_row.setSpacing(10)
        self.transparency_row.addWidget(self.transparency_label, 0)
        self.transparency_row.addWidget(self.transparency_slider, 1)
        layout.addLayout(self.transparency_row)

        self.font_label = QLabel()
        self.font_label.setObjectName("OptionSliderLabel")
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setObjectName("CyanOptionSlider")
        self.font_slider.setRange(8, 14)
        self.font_slider.setValue(self.font_size)
        self.font_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.font_slider.valueChanged.connect(self.on_font_changed)

        self.font_row = QHBoxLayout()
        self.font_row.setContentsMargins(0, 0, 0, 0)
        self.font_row.setSpacing(10)
        self.font_row.addWidget(self.font_label, 0)
        self.font_row.addWidget(self.font_slider, 1)
        layout.addLayout(self.font_row)

        self.default_button = QPushButton("Default")
        self.frame_button = QPushButton("Frame color")
        self.text_button = QPushButton("Text color")
        self.bg_button = QPushButton("Background color")

        self.general_table_button = QPushButton("General Table")
        self.clear_data_button = QPushButton("Clear local data/cache")
        self.clear_data_button.setObjectName("DangerButton")
        self.health_button = QPushButton("Health Check")

        self.default_button.clicked.connect(self.reset_defaults)
        self.frame_button.clicked.connect(self.pick_frame_color)
        self.text_button.clicked.connect(self.pick_text_color)
        self.bg_button.clicked.connect(self.pick_bg_color)

        self.general_table_button.clicked.connect(self.generalTableRequested.emit)
        self.clear_data_button.clicked.connect(self.clearDataRequested.emit)
        self.health_button.clicked.connect(self.healthCheckRequested.emit)

        self.button_wrap = FlowLayout(hspacing=8, vspacing=6)
        for button in (
            self.default_button,
            self.frame_button,
            self.text_button,
            self.bg_button,
            self.general_table_button,
            self.clear_data_button,
            self.health_button,
        ):
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.button_wrap.addWidget(button)

        self.blur_check = QCheckBox("Blur")
        self.blur_check.setChecked(bool(self.blur))
        self.blur_check.toggled.connect(self.on_blur_toggled)
        layout.addWidget(self.blur_check)

        layout.addLayout(self.button_wrap)

        layout.addStretch()

        self.update_labels()
        self.apply_local_style()

        # Force one clean layout pass after the widget receives its first real
        # width. This prevents the initial Options page from drawing the button
        # wrap at the bottom / hiding the sliders until a manual resize.
        QTimer.singleShot(0, self.refresh_layout)
        QTimer.singleShot(80, self.refresh_layout)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.refresh_layout)

    def refresh_layout(self):
        if hasattr(self, "button_wrap"):
            self.button_wrap.invalidate()
        if hasattr(self, "content"):
            self.content.updateGeometry()
            self.content.adjustSize()
        if hasattr(self, "scroll_area"):
            self.scroll_area.viewport().update()

    def make_line(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #343840;")
        return line

    def update_labels(self):
        self.transparency_label.setText(f"Transparency: {self.transparency}%")
        self.font_label.setText(f"Font size: {self.font_size} pt")

    def apply_local_style(self):
        self.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                color: {self.text_color};
                font-size: {self.font_size}pt;
            }}

            QScrollArea {{
                background: transparent;
                border: none;
            }}

            QScrollArea::viewport {{
                background: transparent;
                border: none;
            }}

            QWidget#OptionsContent {{
                background: transparent;
                border: none;
            }}

            QLabel {{
                color: {self.text_color};
                background: transparent;
                font-size: {self.font_size}pt;
            }}

            QPushButton {{
                background-color: rgba(24, 26, 30, 180);
                color: {self.text_color};
                border: 1px solid {self.frame_color};
                padding: 4px 8px;
                font-size: {self.font_size}pt;
            }}

            QPushButton:hover {{
                background-color: rgba(42, 46, 54, 220);
                color: #ffffff;
                border: 1px solid #69707a;
            }}

            QPushButton#DangerButton {{
                background-color: rgba(115, 32, 36, 210);
                color: #ffffff;
                border: 1px solid rgba(220, 82, 88, 220);
            }}

            QPushButton#DangerButton:hover {{
                background-color: rgba(158, 42, 48, 235);
                color: #ffffff;
                border: 1px solid rgba(255, 125, 130, 245);
            }}

            QCheckBox {{
                color: {self.text_color};
                background: transparent;
                spacing: 7px;
                font-size: {self.font_size}pt;
            }}

            QCheckBox::indicator {{
                width: 13px;
                height: 13px;
                border: 1px solid {self.frame_color};
                background: rgba(24, 26, 30, 180);
            }}

            QCheckBox::indicator:checked {{
                background: #39c7b5;
                border: 1px solid #a9f5e0;
            }}

            QLabel#OptionSliderLabel {{
                color: {self.text_color};
                background: transparent;
                font-size: {self.font_size}pt;
                min-width: 112px;
            }}

            QSlider#CyanOptionSlider {{
                background: transparent;
                min-height: 24px;
                max-height: 24px;
            }}

            QSlider#CyanOptionSlider::groove:horizontal {{
                height: 3px;
                background: rgba(214, 214, 214, 90);
                border: none;
                border-radius: 2px;
            }}

            QSlider#CyanOptionSlider::sub-page:horizontal {{
                background: #39c7b5;
                border: none;
                border-radius: 2px;
            }}

            QSlider#CyanOptionSlider::add-page:horizontal {{
                background: rgba(214, 214, 214, 90);
                border: none;
                border-radius: 2px;
            }}

            QSlider#CyanOptionSlider::handle:horizontal {{
                background: #39c7b5;
                width: 16px;
                height: 16px;
                margin: -7px 0px;
                border-radius: 8px;
                border: 2px solid rgba(215, 255, 248, 235);
            }}

            QSlider#CyanOptionSlider::handle:horizontal:hover {{
                background: #56ead7;
                border: 2px solid #ffffff;
            }}

            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0px;
            }}

            QScrollBar::handle:vertical {{
                background: rgba(120, 130, 145, 95);
                min-height: 20px;
                border-radius: 3px;
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                width: 0px;
                background: transparent;
            }}

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            QScrollBar:horizontal {{
                height: 0px;
                background: transparent;
            }}
        """)

    def set_values(
        self,
        transparency,
        blur,
        font_size,
        frame_color,
        text_color,
        bg_color,
        emit=False,
    ):
        self._loading_values = True

        self.transparency = max(0, min(100, int(transparency)))
        self.blur = 1 if int(blur) else 0
        self.font_size = max(8, min(14, int(font_size)))
        self.frame_color = str(frame_color).lower()
        self.text_color = str(text_color).lower()
        self.bg_color = str(bg_color).lower()

        self.transparency_slider.setValue(self.transparency)
        self.font_slider.setValue(self.font_size)
        self.blur_check.setChecked(bool(self.blur))

        self._loading_values = False

        self.update_labels()
        self.apply_local_style()

        if emit:
            self.emit_settings()

    def emit_settings(self):
        if self._loading_values:
            return

        self.update_labels()
        self.apply_local_style()

        self.settingsChanged.emit(
            self.transparency,
            self.blur,
            self.font_size,
            self.frame_color,
            self.text_color,
            self.bg_color,
        )

    def on_transparency_changed(self, value):
        self.transparency = int(value)
        self.emit_settings()

    def on_blur_toggled(self, checked):
        self.blur = 1 if checked else 0
        self.emit_settings()

    def on_font_changed(self, value):
        self.font_size = int(value)
        self.emit_settings()

    def reset_defaults(self):
        defaults = DEFAULT_UI_SETTINGS
        self.set_values(
            defaults["transparency"],
            defaults["blur"],
            defaults["font_size"],
            defaults["frame_color"],
            defaults["text_color"],
            defaults["bg_color"],
            emit=True,
        )

    def pick_frame_color(self):
        color = QColorDialog.getColor(QColor(self.frame_color), self)
        if color.isValid():
            self.frame_color = color.name().lower()
            self.emit_settings()

    def pick_text_color(self):
        color = QColorDialog.getColor(QColor(self.text_color), self)
        if color.isValid():
            self.text_color = color.name().lower()
            self.emit_settings()

    def pick_bg_color(self):
        color = QColorDialog.getColor(QColor(self.bg_color), self)
        if color.isValid():
            self.bg_color = color.name().lower()
            self.emit_settings()
