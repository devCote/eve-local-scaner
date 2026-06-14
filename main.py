import sys
import traceback
import sqlite3

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from paths import USER_DATA_DIR, ensure_user_data_dirs, icon_path
from style import apply_eve_style
from local_intel_updater import ensure_local_intel_ready
from local_intel_db import get_db_path
from logger_setup import setup_file_logging
from crash_handler import install_crash_handler
from app_fonts import make_app_font, resolve_app_font_family


def set_windows_app_id():
    if sys.platform != "win32":
        return

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "EVE.LocalIntel.Scanner"
        )
    except Exception as e:
        print("AppUserModelID error:", e)


def get_app_icon() -> QIcon:
    for name in ("app.ico", "app.svg", "app.png"):
        icon = QIcon(icon_path(name))
        if not icon.isNull():
            return icon

    return QIcon()


class StartupUpdateWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Intel Scanner")
        self.setFixedSize(520, 165)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

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
                background-color: #0b0b0b;
                color: #d6d6d6;
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
                background-color: #181a1e;
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
        self.status.setText(str(text))

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
                    self.progressChanged.emit(max(0, min(100, percent)))

            ensure_local_intel_ready(progress_callback=callback)
            self.statusChanged.emit("Local intel database is ready. Opening app...")
            self.progressChanged.emit(100)
            self.finishedOk.emit()

        except Exception:
            error_text = traceback.format_exc()
            print("[STARTUP UPDATER ERROR]")
            print(error_text)
            self.failed.emit(error_text)



def local_db_is_usable() -> bool:
    """Return True only when local SQLite has real killmail data.

    This prevents the app from opening with an empty DB after a startup updater
    failure on first install.
    """
    try:
        db_path = get_db_path()

        if not db_path.exists() or db_path.stat().st_size < 1024:
            return False

        conn = sqlite3.connect(str(db_path), timeout=5)

        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='killmails'"
            )

            if not cur.fetchone():
                return False

            cur.execute("SELECT COUNT(*) FROM killmails")
            count = int(cur.fetchone()[0] or 0)
            return count > 0

        finally:
            conn.close()

    except Exception as e:
        print(f"[STARTUP] local DB usability check failed: {e}")
        return False


def main() -> int:
    log_path = setup_file_logging()
    install_crash_handler(show_message_box=False)
    set_windows_app_id()
    ensure_user_data_dirs()

    app = QApplication(sys.argv)
    app.setFont(make_app_font(10))
    resolve_app_font_family()

    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    lock_path = USER_DATA_DIR / "eve_local_intel_scanner.lock"
    app_lock = QLockFile(str(lock_path))
    app_lock.setStaleLockTime(0)

    if not app_lock.tryLock(100):
        QMessageBox.information(
            None,
            "EVE Local Intel Scanner",
            "Application is already running.",
        )
        return 0

    apply_eve_style(app)

    startup = StartupUpdateWindow()
    if not app_icon.isNull():
        startup.setWindowIcon(app_icon)

    startup.show()
    startup.set_status(f"Checking local intel database...\nLog: {log_path}")

    state = {
        "main_window": None,
        "worker": None,
        "lock": app_lock,
    }

    def open_main_window():
        try:
            startup.set_status("Opening main window...")
            startup.set_progress(100)
            app.processEvents()

            # IMPORTANT: import UI only after DB updater is done.
            # This prevents the app from skipping startup DB update.
            from ui import EveLocalScanner

            window = EveLocalScanner()
            if not app_icon.isNull():
                window.setWindowIcon(app_icon)

            state["main_window"] = window
            window.show()
            window.raise_()
            window.activateWindow()

            startup.close()

        except Exception as e:
            error_text = str(e)
            print(f"[STARTUP] failed to open main window: {error_text}")
            startup.set_status(f"Failed to open main window: {error_text}")
            QMessageBox.critical(
                startup,
                "EVE Local Intel Scanner",
                f"Failed to open main window:\n\n{error_text}",
            )

    def on_update_failed(error_text: str):
        print("[STARTUP] local DB update failed:")
        print(error_text)

        if local_db_is_usable():
            startup.set_status(
                "Local DB update failed, but an existing usable database was found.\n"
                "Opening app with cached data..."
            )
            startup.set_progress(100)
            QTimer.singleShot(1200, open_main_window)
            return

        startup.set_status(
            "Local DB update failed and no usable database was found.\n"
            "Check your internet connection and logs, then restart the app."
        )
        startup.set_progress(0)

        QMessageBox.critical(
            startup,
            "EVE Local Intel Scanner",
            "Local DB update failed and no usable database was found.\n\n"
            "The app will not open with an empty database.\n\n"
            f"Details:\n{str(error_text)[:3000]}",
        )


    worker = LocalIntelUpdateThread()
    state["worker"] = worker

    worker.statusChanged.connect(startup.set_status)
    worker.progressChanged.connect(startup.set_progress)
    worker.finishedOk.connect(lambda: QTimer.singleShot(350, open_main_window))
    worker.failed.connect(on_update_failed)
    worker.start()

    exit_code = app.exec()

    if worker.isRunning():
        worker.quit()
        worker.wait(3000)

    try:
        app_lock.unlock()
    except Exception:
        pass

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
