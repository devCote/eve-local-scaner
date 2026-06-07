import os
import sys
import subprocess
import webbrowser


def is_wsl() -> bool:
    try:
        if "microsoft" in os.uname().release.lower():
            return True
    except Exception:
        pass

    return False


def open_url(url: str):
    if not url:
        return

    try:
        # WSL -> открываем браузер Windows по умолчанию
        if is_wsl():
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        # Windows Python
        if sys.platform == "win32":
            os.startfile(url)
            return

        # Linux обычный
        webbrowser.open(url)

    except Exception as e:
        print("Open browser error:", e)
