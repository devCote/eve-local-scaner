from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton


class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        self.parent_window = parent

        self.setObjectName("TitleBar")
        self.setFixedHeight(30)

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self.title = QLabel("EVE LOCAL INTEL SCANNER")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title.setStyleSheet("""
            QLabel {
                color: #FF9900;
                font-weight: bold;
                font-size: 10pt;
                letter-spacing: 1px;
                background-color: transparent;
            }
        """)

        self.top_button = QPushButton("TOP")
        self.top_button.setCheckable(True)

        self.minimize_button = QPushButton("—")
        self.close_button = QPushButton("×")

        for button in [
            self.top_button,
            self.minimize_button,
            self.close_button,
        ]:
            button.setFixedSize(34, 22)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 34, 40, 180);
                    color: #D0D0D0;
                    border: 1px solid #3A4048;
                    font-size: 9pt;
                    font-weight: bold;
                    padding: 0px;
                }

                QPushButton:hover {
                    background-color: #FF9900;
                    color: #000000;
                }
            """)

        self.top_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 34, 40, 180);
                color: #D0D0D0;
                border: 1px solid #3A4048;
                font-size: 8pt;
                font-weight: bold;
                padding: 0px;
            }

            QPushButton:hover {
                background-color: #FF9900;
                color: #000000;
            }

            QPushButton:checked {
                background-color: #FF9900;
                color: #000000;
                border: 1px solid #FF9900;
            }
        """)

        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 34, 40, 180);
                color: #D0D0D0;
                border: 1px solid #3A4048;
                font-size: 9pt;
                font-weight: bold;
                padding: 0px;
            }

            QPushButton:hover {
                background-color: #AA2222;
                color: #FFFFFF;
            }
        """)

        self.top_button.toggled.connect(self.parent_window.toggle_always_on_top)
        self.minimize_button.clicked.connect(self.parent_window.showMinimized)
        self.close_button.clicked.connect(self.parent_window.close)

        layout.addWidget(self.title)
        layout.addStretch()
        layout.addWidget(self.top_button)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.close_button)

        self.setLayout(layout)

        self.setStyleSheet("""
            QWidget#TitleBar {
                background-color: rgba(10, 12, 14, 245);
                border-bottom: 1px solid #FF9900;
            }
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
