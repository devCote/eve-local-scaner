from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton


class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        self.parent_window = parent
        self.setObjectName("TitleBar")
        self.setFixedHeight(22)

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 1, 4, 1)
        layout.setSpacing(3)

        self.title = QLabel("Overview (Local Intel)")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.top_button = QPushButton("●")
        self.top_button.setCheckable(True)
        self.minimize_button = QPushButton("—")
        self.close_button = QPushButton("×")

        for button in [self.top_button, self.minimize_button, self.close_button]:
            button.setFixedSize(20, 16)
            button.setCursor(Qt.PointingHandCursor)

        self.top_button.toggled.connect(self.parent_window.toggle_always_on_top)
        self.minimize_button.clicked.connect(self.parent_window.showMinimized)
        self.close_button.clicked.connect(self.parent_window.close)

        layout.addWidget(self.title)
        layout.addStretch()
        layout.addWidget(self.top_button)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.close_button)
        self.setLayout(layout)

        self.apply_style("#3D424A", "#D6D8DC", 8, 220)

    def apply_style(self, frame_color, text_color, font_size=8, alpha=220):
        self.title.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-size: {font_size}pt;
                font-weight: normal;
                background-color: transparent;
            }}
        """)

        button_style = f"""
            QPushButton {{
                background-color: rgba(18, 20, 24, {alpha});
                color: #AEB4BC;
                border: 1px solid {frame_color};
                padding: 0px;
                font-size: {max(7, font_size - 1)}pt;
            }}

            QPushButton:hover {{
                background-color: rgba(42, 46, 54, {min(255, alpha + 30)});
                color: #FFFFFF;
                border: 1px solid #68707A;
            }}

            QPushButton:checked {{
                background-color: rgba(35, 65, 65, {min(255, alpha + 30)});
                color: #9FFFF0;
                border: 1px solid #4D8A86;
            }}
        """

        close_style = f"""
            QPushButton {{
                background-color: rgba(18, 20, 24, {alpha});
                color: #AEB4BC;
                border: 1px solid {frame_color};
                padding: 0px;
                font-size: {font_size}pt;
            }}

            QPushButton:hover {{
                background-color: rgba(100, 36, 36, {min(255, alpha + 30)});
                color: #FFFFFF;
                border: 1px solid #A05A5A;
            }}
        """

        self.top_button.setStyleSheet(button_style)
        self.minimize_button.setStyleSheet(button_style)
        self.close_button.setStyleSheet(close_style)

        self.setStyleSheet(f"""
            QWidget#TitleBar {{
                background-color: transparent;
                border: none;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.parent_window.windowHandle()
            if window:
                window.startSystemMove()
            event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()
