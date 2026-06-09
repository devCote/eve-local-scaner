from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel


class EveTabs(QWidget):
    tabChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.buttons = {}

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

        self.apply_colors("#2F343B", "#C7C9CC", 10, "#0b0b0b")

    def set_active(self, name):
        for tab_name, button in self.buttons.items():
            button.setChecked(tab_name == name)

        self.tabChanged.emit(name)

    def set_linked_count(self, count):
        if count > 0:
            self.linked_label.setText(f"linked pilots: {count}")
        else:
            self.linked_label.setText("")

    def apply_colors(self, frame_color, text_color, font_size=10, bg_color="#0b0b0b"):
        self.setStyleSheet(f"""
            QWidget#EveTabs {{
                background-color: rgba(10, 11, 13, 180);
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
