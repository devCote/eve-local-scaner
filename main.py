import os
import sys

# IMPORTANT: QtWebEngine/Chromium flags must be set before QApplication
# and before any QWebEngineView/QWebEnginePage is created/imported.
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-gpu "
    "--disable-gpu-compositing "
    "--disable-gpu-rasterization "
    "--disable-accelerated-2d-canvas "
    "--disable-accelerated-video-decode "
    "--disable-dev-shm-usage "
    "--use-angle=swiftshader "
    "--no-sandbox"
)

os.environ["QT_OPENGL"] = "software"

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from paths import icon_path
from style import apply_eve_style
from local_intel_updater import ensure_local_intel_ready


def set_windows_app_id():
    if sys.platform != "win32":
        return

    try:
        import ctypes

        app_id = "EVE.LocalIntel.Scanner"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as e:
        print("AppUserModelID error:", e)


def get_app_icon() -> QIcon:
    candidates = [
        icon_path("app.ico"),
        icon_path("app.png"),
    ]

    for path in candidates:
        icon = QIcon(path)
        if not icon.isNull():
            return icon

    return QIcon()


class StartupUpdateWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Intel Scanner")
        self.setFixedSize(460, 150)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.title = QLabel("EVE Local Intel Scanner")
        self.title.setObjectName("StartupTitle")

        self.status = QLabel("Checking local intel database...")
        self.status.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)

        self.setStyleSheet("""
            QWidget {
                background-color: rgba(11, 11, 11, 235);
                color: #d6d6d6;
                font-family: "Segoe UI";
                font-size: 10pt;
                border: 1px solid #161616;
            }

            QLabel {
                background: transparent;
                border: none;
                color: #d6d6d6;
            }

            QLabel#StartupTitle {
                color: #A9F5E0;
                font-weight: bold;
                font-size: 11pt;
            }

            QProgressBar {
                background-color: rgba(24, 26, 30, 180);
                border: 1px solid #343840;
                height: 14px;
                text-align: center;
                color: #d6d6d6;
            }

            QProgressBar::chunk {
                background-color: #39C7B5;
            }
        """)

    def set_status(self, text: str):
        self.status.setText(text)

    def set_progress(self, value: int):
        self.progress.setValue(max(0, min(100, int(value))))


class LocalIntelUpdateThread(QThread):
    statusChanged = Signal(str)
    progressChanged = Signal(int)
    finishedOk = Signal()
    failed = Signal(str)

    def run(self):
        try:
            def callback(message, current=None, total=None):
                self.statusChanged.emit(str(message))

                if current is not None and total:
                    percent = int((int(current) / int(total)) * 100)
                    self.progressChanged.emit(percent)

            ensure_local_intel_ready(progress_callback=callback)
            self.progressChanged.emit(100)
            self.statusChanged.emit("Local intel database is ready.")
            self.finishedOk.emit()

        except Exception as e:
            self.failed.emit(str(e))


def cleanup():
    try:
        if os.path.exists("cache.json"):
            os.remove("cache.json")
            print("cache.json removed")
    except Exception as e:
        print("cleanup error:", e)


def main() -> int:
    set_windows_app_id()

    app = QApplication(sys.argv)

    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    apply_eve_style(app)

    startup = StartupUpdateWindow()
    if not app_icon.isNull():
        startup.setWindowIcon(app_icon)
    startup.show()

    state = {
        "main_window": None,
        "worker": None,
    }

    def open_main_window():
        from ui import EveLocalScanner

        window = EveLocalScanner()
        if not app_icon.isNull():
            window.setWindowIcon(app_icon)

        state["main_window"] = window
        window.show()
        startup.close()

    def on_update_failed(error_text: str):
        startup.set_status(f"Local DB update failed, opening app anyway: {error_text}")
        startup.set_progress(100)
        open_main_window()

    worker = LocalIntelUpdateThread()
    state["worker"] = worker

    worker.statusChanged.connect(startup.set_status)
    worker.progressChanged.connect(startup.set_progress)
    worker.finishedOk.connect(open_main_window)
    worker.failed.connect(on_update_failed)
    worker.start()

    exit_code = app.exec()

    if worker.isRunning():
        worker.quit()
        worker.wait(3000)

    cleanup()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
