from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton


class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        self.parent_window = parent

        self.setObjectName("TitleBar")
        self.setFixedHeight(26)

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        self.title = QLabel("Local Intel")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title.setStyleSheet("""
            QLabel {
                color: #E5E8EC;
                font-size: 8.5pt;
                font-weight: normal;
                background-color: transparent;
            }
        """)

        self.top_button = QPushButton("▲")
        self.top_button.setCheckable(True)

        self.minimize_button = QPushButton("—")
        self.close_button = QPushButton("×")

        for button in [
            self.top_button,
            self.minimize_button,
            self.close_button,
        ]:
            button.setFixedSize(22, 18)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(34, 37, 42, 240);
                    color: #D0D3D8;
                    border: 1px solid #555B64;
                    padding: 0px;
                    font-size: 8pt;
                }

                QPushButton:hover {
                    background-color: rgba(58, 62, 70, 250);
                    color: #FFFFFF;
                    border: 1px solid #8F98A3;
                }

                QPushButton:checked {
                    background-color: rgba(75, 80, 90, 250);
                    color: #FFFFFF;
                    border: 1px solid #A0A8B2;
                }
            """)

        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(34, 37, 42, 240);
                color: #D0D3D8;
                border: 1px solid #555B64;
                padding: 0px;
                font-size: 8pt;
            }

            QPushButton:hover {
                background-color: rgba(120, 45, 45, 250);
                color: #FFFFFF;
                border: 1px solid #D07A7A;
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
                background-color: rgba(26, 28, 34, 248);
                border-top: 1px solid #666C75;
                border-left: 1px solid #666C75;
                border-right: 1px solid #2B2E34;
                border-bottom: 1px solid #1D1F24;
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
