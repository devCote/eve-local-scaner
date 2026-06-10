from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView


class ZKillViewer(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("zKill Viewer")
        self.resize(1100, 800)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.web = QWebEngineView()
        layout.addWidget(self.web)

        self.setLayout(layout)

    def open_url(self, url: str):
        self.web.load(QUrl(url))
        self.show()
