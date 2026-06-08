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
)


class OptionsPanel(QWidget):
    # transparency_percent, blur_percent, font_size, frame_color, text_color, bg_color
    settingsChanged = Signal(int, int, int, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.transparency = 20      # 0 = opaque, 100 = fully transparent
        self.blur = 8               # 0 = off, 100 = strongest available tint/blur
        self.font_size = 8
        self.frame_color = "#444A52"
        self.text_color = "#C7C9CC"
        self.bg_color = "#07080A"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(9)

        title = QLabel("UI Options")
        title.setObjectName("OptionsTitle")
        layout.addWidget(title)
        layout.addWidget(self.make_line())

        self.transparency_label = QLabel()
        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(0, 100)
        self.transparency_slider.setValue(self.transparency)
        self.transparency_slider.valueChanged.connect(self.on_transparency_changed)
        layout.addWidget(self.transparency_label)
        layout.addWidget(self.transparency_slider)

        self.blur_label = QLabel()
        self.blur_slider = QSlider(Qt.Horizontal)
        self.blur_slider.setRange(0, 100)
        self.blur_slider.setValue(self.blur)
        self.blur_slider.valueChanged.connect(self.on_blur_changed)
        layout.addWidget(self.blur_label)
        layout.addWidget(self.blur_slider)

        self.font_label = QLabel()
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(7, 14)
        self.font_slider.setValue(self.font_size)
        self.font_slider.valueChanged.connect(self.on_font_changed)
        layout.addWidget(self.font_label)
        layout.addWidget(self.font_slider)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(8)

        self.frame_button = QPushButton("Frame color")
        self.text_button = QPushButton("Text color")
        self.bg_button = QPushButton("Background color")

        self.frame_button.clicked.connect(self.pick_frame_color)
        self.text_button.clicked.connect(self.pick_text_color)
        self.bg_button.clicked.connect(self.pick_bg_color)

        color_row.addWidget(self.frame_button)
        color_row.addWidget(self.text_button)
        color_row.addWidget(self.bg_button)
        color_row.addStretch()
        layout.addLayout(color_row)

        self.preview = QLabel("Preview: EVE Local Intel Scanner")
        self.preview.setFixedHeight(34)
        self.preview.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.preview)
        layout.addStretch()

        self.update_labels()
        self.update_preview()
        self.apply_local_style()

    def alpha_from_transparency(self):
        # 0% transparency = 255 alpha, 100% transparency = 0 alpha
        return max(0, min(255, int(round(255 * (100 - self.transparency) / 100))))

    def make_line(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #343840;")
        return line

    def update_labels(self):
        self.transparency_label.setText(
            f"Transparency: {self.transparency}%  (0% = opaque, 100% = invisible)"
        )
        self.blur_label.setText(f"Blur: {self.blur}%")
        self.font_label.setText(f"Font size: {self.font_size} pt")

    def update_preview(self):
        alpha = self.alpha_from_transparency()
        color = QColor(self.bg_color)
        self.preview.setStyleSheet(f"""
            QLabel {{
                color: {self.text_color};
                background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {alpha});
                border: 1px solid {self.frame_color};
                font-size: {self.font_size}pt;
            }}
        """)

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
                color: #FFFFFF;
                border: 1px solid #69707A;
            }}

            QSlider::groove:horizontal {{
                height: 4px;
                background: rgba(40, 45, 52, 180);
                border: 1px solid {self.frame_color};
            }}

            QSlider::handle:horizontal {{
                background: #8F959C;
                width: 10px;
                margin: -5px 0;
                border: 1px solid {self.text_color};
            }}
        """)

    def emit_settings(self):
        self.update_labels()
        self.update_preview()
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
        self.transparency = value
        self.emit_settings()

    def on_blur_changed(self, value):
        self.blur = value
        self.emit_settings()

    def on_font_changed(self, value):
        self.font_size = value
        self.emit_settings()

    def pick_frame_color(self):
        color = QColorDialog.getColor(QColor(self.frame_color), self)
        if color.isValid():
            self.frame_color = color.name()
            self.emit_settings()

    def pick_text_color(self):
        color = QColorDialog.getColor(QColor(self.text_color), self)
        if color.isValid():
            self.text_color = color.name()
            self.emit_settings()

    def pick_bg_color(self):
        color = QColorDialog.getColor(QColor(self.bg_color), self)
        if color.isValid():
            self.bg_color = color.name()
            self.emit_settings()
