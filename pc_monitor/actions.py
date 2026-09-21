"""
actions.py - Cac hanh dong dieu khien may tinh: chup man hinh, khoa may,
tat may, khoi dong lai. Code rieng cho tung OS vi day la thao tac he thong,
khong co API chung cho ca 3 OS.
"""

import os
import platform
import subprocess
from pathlib import Path

from . import config


def _os() -> str:
    return platform.system()  # "Windows" | "Darwin" | "Linux"


# --------------------------------- SCREENSHOT --------------------------------

def take_screenshot() -> tuple:
    """Chup man hinh, luu vao config.SCREENSHOT_TMP.
    Tra ve (True, duong_dan) hoac (False, thong_bao_loi)."""
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            # Chup man hinh dau tien (monitor[1]; monitor[0] la "toan bo cac man hinh gop lai")
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(monitor)
            mss.tools.to_png(shot.rgb, shot.size, output=str(config.SCREENSHOT_TMP))
        return True, str(config.SCREENSHOT_TMP)
    except Exception as e:
        return False, f"Khong chup duoc man hinh: {e}"


# ------------------------------------ LOCK ------------------------------------

def lock_screen() -> tuple:
    """Khoa man hinh. Tra ve (True, thong_bao) hoac (False, loi)."""
    system = _os()
    try:
        if system == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return True, "Da khoa man hinh."

        elif system == "Darwin":
            # Cach chuan tren macOS moi: yeu cau man hinh ngu ngay (co man hinh khoa)
            subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to keystroke "q" using {control down, command down}'],
                check=True, timeout=10,
            )
            return True, "Da gui lenh khoa man hinh."

        elif system == "Linux":
            # Thu lan luot cac cach pho bien tuy desktop environment
            candidates = [
                ["loginctl", "lock-session"],
                ["xdg-screensaver", "lock"],
                ["gnome-screensaver-command", "--lock"],
                ["dm-tool", "lock"],
            ]
            for cmd in candidates:
                try:
                    subprocess.run(cmd, check=True, timeout=10,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True, f"Da khoa man hinh (dung lenh: {' '.join(cmd)})."
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            return False, "Khong tim thay lenh khoa man hinh phu hop voi desktop environment nay."

        return False, f"He dieu hanh {system} chua duoc ho tro."
    except Exception as e:
        return False, f"Loi khi khoa man hinh: {e}"


# ------------------------------ SHUTDOWN / RESTART -----------------------------

def shutdown_now() -> tuple:
    system = _os()
    try:
        if system == "Windows":
            subprocess.run(["shutdown", "/s", "/t", "5"], check=True)
            return True, "May se tat sau 5 giay."

        elif system == "Darwin":
            # Khong can sudo: goi qua System Events (nguoi dung dang dang nhap
            # se thay hop thoai xac nhan neu he thong yeu cau)
            subprocess.run(
                ["osascript", "-e", 'tell app "System Events" to shut down'],
                check=True, timeout=10,
            )
            return True, "Da gui lenh tat may."

        elif system == "Linux":
            # Can quyen; neu chay khong phai root/sudo se bao loi ro rang
            subprocess.run(["shutdown", "-h", "+0"], check=True, timeout=10)
            return True, "Da gui lenh tat may."

        return False, f"He dieu hanh {system} chua duoc ho tro."
    except subprocess.CalledProcessError as e:
        return False, f"Khong the tat may (thieu quyen?): {e}"
    except Exception as e:
        return False, f"Loi khi tat may: {e}"


def restart_now() -> tuple:
    system = _os()
    try:
        if system == "Windows":
            subprocess.run(["shutdown", "/r", "/t", "5"], check=True)
            return True, "May se khoi dong lai sau 5 giay."

        elif system == "Darwin":
            subprocess.run(
                ["osascript", "-e", 'tell app "System Events" to restart'],
                check=True, timeout=10,
            )
            return True, "Da gui lenh khoi dong lai."

        elif system == "Linux":
            subprocess.run(["shutdown", "-r", "+0"], check=True, timeout=10)
            return True, "Da gui lenh khoi dong lai."

        return False, f"He dieu hanh {system} chua duoc ho tro."
    except subprocess.CalledProcessError as e:
        return False, f"Khong the khoi dong lai (thieu quyen?): {e}"
    except Exception as e:
        return False, f"Loi khi khoi dong lai: {e}"


# --------------------------------------- NOTE ---------------------------------

def append_note(text: str) -> tuple:
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(config.NOTE_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")
        return True, f"Da luu ghi chu vao {config.NOTE_FILE.name}"
    except Exception as e:
        return False, f"Khong luu duoc ghi chu: {e}"
