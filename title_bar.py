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
        self.title.setStyleSheet("""
            QLabel {
                color: #D6D8DC;
                font-size: 8pt;
                font-weight: normal;
                background-color: transparent;
            }
        """)

        self.top_button = QPushButton("●")
        self.top_button.setCheckable(True)

        self.minimize_button = QPushButton("—")
        self.close_button = QPushButton("×")

        for button in [self.top_button, self.minimize_button, self.close_button]:
            button.setFixedSize(20, 16)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(18, 20, 24, 235);
                    color: #AEB4BC;
                    border: 1px solid #343840;
                    padding: 0px;
                    font-size: 7.5pt;
                }

                QPushButton:hover {
                    background-color: rgba(42, 46, 54, 245);
                    color: #FFFFFF;
                    border: 1px solid #68707A;
                }

                QPushButton:checked {
                    background-color: rgba(35, 65, 65, 245);
                    color: #9FFFF0;
                    border: 1px solid #4D8A86;
                }
            """)

        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(18, 20, 24, 235);
                color: #AEB4BC;
                border: 1px solid #343840;
                padding: 0px;
                font-size: 8pt;
            }

            QPushButton:hover {
                background-color: rgba(100, 36, 36, 245);
                color: #FFFFFF;
                border: 1px solid #A05A5A;
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
                background-color: rgba(12, 13, 15, 248);
                border-top: 1px solid #3D424A;
                border-left: 1px solid #3D424A;
                border-right: 1px solid #101216;
                border-bottom: 1px solid #07080A;
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
