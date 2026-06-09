from PySide6.QtCore import Qt, Signal
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
)

from user_settings import DEFAULT_UI_SETTINGS


class OptionsPanel(QWidget):
    # transparency, blur, font_size, frame_color, text_color, bg_color
    settingsChanged = Signal(int, int, int, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.transparency = DEFAULT_UI_SETTINGS["transparency"]
        self.blur = DEFAULT_UI_SETTINGS["blur"]
        self.font_size = DEFAULT_UI_SETTINGS["font_size"]
        self.frame_color = DEFAULT_UI_SETTINGS["frame_color"]
        self.text_color = DEFAULT_UI_SETTINGS["text_color"]
        self.bg_color = DEFAULT_UI_SETTINGS["bg_color"]

        self._loading_values = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.title = QLabel("UI Options")
        self.title.setObjectName("OptionsTitle")
        layout.addWidget(self.title)

        layout.addWidget(self.make_line())

        self.transparency_label = QLabel()
        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(0, 100)
        self.transparency_slider.setValue(self.transparency)
        self.transparency_slider.valueChanged.connect(self.on_transparency_changed)

        layout.addWidget(self.transparency_label)
        layout.addWidget(self.transparency_slider)

        self.font_label = QLabel()
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(7, 16)
        self.font_slider.setValue(self.font_size)
        self.font_slider.valueChanged.connect(self.on_font_changed)

        layout.addWidget(self.font_label)
        layout.addWidget(self.font_slider)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(8)

        self.default_button = QPushButton("Default")
        self.frame_button = QPushButton("Frame color")
        self.text_button = QPushButton("Text color")
        self.bg_button = QPushButton("Background color")

        self.default_button.clicked.connect(self.reset_defaults)
        self.frame_button.clicked.connect(self.pick_frame_color)
        self.text_button.clicked.connect(self.pick_text_color)
        self.bg_button.clicked.connect(self.pick_bg_color)

        color_row.addWidget(self.default_button)
        color_row.addWidget(self.frame_button)
        color_row.addWidget(self.text_button)
        color_row.addWidget(self.bg_button)
        color_row.addStretch()
        layout.addLayout(color_row)

        self.blur_check = QCheckBox("Blur")
        self.blur_check.setChecked(bool(self.blur))
        self.blur_check.toggled.connect(self.on_blur_toggled)
        layout.addWidget(self.blur_check)

        layout.addStretch()

        self.update_labels()
        self.apply_local_style()

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

            QLabel {{
                color: {self.text_color};
                background: transparent;
                font-size: {self.font_size}pt;
            }}

            QLabel#OptionsTitle {{
                color: #A9F5E0;
                font-size: {self.font_size + 1}pt;
                font-weight: bold;
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

            QSlider::groove:horizontal {{
                height: 4px;
                background: rgba(40, 45, 52, 180);
                border: 1px solid {self.frame_color};
            }}

            QSlider::handle:horizontal {{
                background: #8f959c;
                width: 10px;
                margin: -5px 0;
                border: 1px solid {self.text_color};
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
        self.font_size = max(7, min(16, int(font_size)))
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
