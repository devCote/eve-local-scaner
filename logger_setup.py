from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from paths import USER_DATA_DIR, ensure_user_data_dirs


class SafeLogStream:
    """Very small stdout/stderr redirector that does NOT use logging module.

    This avoids PyInstaller windowed recursion:
    logging.emit -> handleError -> sys.stderr -> logging again -> recursion.
    """

    def __init__(self, log_path: Path, original_stream=None, prefix: str = ""):
        self.log_path = log_path
        self.original_stream = original_stream
        self.prefix = prefix
        self._buffer = ""

    def write(self, message):
        if not message:
            return

        try:
            text = str(message)

            # Write to real console only if it exists.
            if self.original_stream is not None and hasattr(self.original_stream, "write"):
                try:
                    self.original_stream.write(text)
                    self.original_stream.flush()
                except Exception:
                    pass

            self._buffer += text

            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                self._write_line(line.rstrip())

        except Exception:
            # Never crash app because of logging.
            pass

    def flush(self):
        try:
            if self._buffer.strip():
                self._write_line(self._buffer.strip())
                self._buffer = ""

            if self.original_stream is not None and hasattr(self.original_stream, "flush"):
                try:
                    self.original_stream.flush()
                except Exception:
                    pass
        except Exception:
            pass

    def isatty(self):
        return False

    def _write_line(self, line: str):
        if not line:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{self.prefix}] " if self.prefix else ""

        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(f"{timestamp} {prefix}{line}\n")
        except Exception:
            pass


def cleanup_old_logs(logs_dir: Path, keep: int = 10):
    try:
        logs = sorted(
            logs_dir.glob("eve-local-scanner-*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for path in logs[keep:]:
            try:
                path.unlink()
            except Exception:
                pass

    except Exception:
        pass


def setup_file_logging() -> Path | None:
    """Safe file logging for python main.py and PyInstaller windowed exe.

    Does not use logging.StreamHandler and does not redirect via logging module.
    """
    try:
        ensure_user_data_dirs()

        logs_dir = USER_DATA_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = logs_dir / f"eve-local-scanner-{timestamp}.log"

        original_stdout = getattr(sys, "__stdout__", None)
        original_stderr = getattr(sys, "__stderr__", None)

        # Create file immediately.
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] Logging started\n")
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] Log file: {log_path}\n")

        sys.stdout = SafeLogStream(log_path, original_stdout, "STDOUT")
        sys.stderr = SafeLogStream(log_path, original_stderr, "STDERR")

        cleanup_old_logs(logs_dir, keep=10)

        return log_path

    except Exception:
        # Logging must never prevent app startup.
        try:
            traceback.print_exc()
        except Exception:
            pass

        return None
