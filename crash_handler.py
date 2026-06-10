from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from paths import USER_DATA_DIR, ensure_user_data_dirs


def get_crash_dir() -> Path:
    ensure_user_data_dirs()
    crash_dir = USER_DATA_DIR / "logs"
    crash_dir.mkdir(parents=True, exist_ok=True)
    return crash_dir


def cleanup_old_crashes(crash_dir: Path, keep: int = 20):
    try:
        crashes = sorted(
            crash_dir.glob("crash-*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for path in crashes[keep:]:
            try:
                path.unlink()
            except Exception:
                pass

    except Exception:
        pass


def write_crash_log(exc_type, exc_value, exc_traceback, source: str = "main") -> Path | None:
    try:
        crash_dir = get_crash_dir()
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        crash_path = crash_dir / f"crash-{timestamp}-{source}.log"

        with crash_path.open("w", encoding="utf-8") as f:
            f.write("EVE Local Intel Scanner crash report\n")
            f.write(f"Time: {datetime.now().isoformat(timespec='seconds')}\n")
            f.write(f"Source: {source}\n")
            f.write("\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)

        cleanup_old_crashes(crash_dir, keep=20)
        return crash_path

    except Exception:
        return None


def install_crash_handler(show_message_box: bool = False):
    """Install global crash handlers for main thread and worker threads.

    This is intentionally lightweight and safe for PyInstaller windowed builds.
    """

    def excepthook(exc_type, exc_value, exc_traceback):
        crash_path = write_crash_log(exc_type, exc_value, exc_traceback, source="main")

        try:
            print(f"[CRASH] unhandled exception saved: {crash_path}")
        except Exception:
            pass

        if show_message_box:
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(
                    None,
                    "EVE Local Intel Scanner crashed",
                    f"Unhandled exception was saved to:\n{crash_path}",
                )
            except Exception:
                pass

        # Keep default behavior for console runs.
        try:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        except Exception:
            pass

    def threading_excepthook(args):
        crash_path = write_crash_log(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            source=f"thread-{getattr(args.thread, 'name', 'unknown')}",
        )

        try:
            print(f"[CRASH] thread exception saved: {crash_path}")
        except Exception:
            pass

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        threading.excepthook = threading_excepthook
