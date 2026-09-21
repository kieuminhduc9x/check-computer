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

def _lock_note() -> str:
    try:
        from . import system_info
        locked = system_info.is_screen_locked()
    except Exception:
        locked = None
    if locked is True:
        return " Man hinh dang khoa — van force tat/restart, khong cho app hoi."
    if locked is False:
        return ""
    return " (khong xac dinh man hinh co dang khoa khong)"


def _enable_windows_shutdown_privilege() -> bool:
    """Bat SeShutdownPrivilege de ExitWindowsEx chay duoc ca khi khoa man hinh."""
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
    TOKEN_ADJUST_PRIVILEGES = 0x0020
    TOKEN_QUERY = 0x0008
    SE_PRIVILEGE_ENABLED = 0x00000002

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("PrivilegeCount", wintypes.DWORD),
                    ("Privileges", LUID_AND_ATTRIBUTES * 1)]

    h_token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
        ctypes.byref(h_token),
    ):
        return False
    luid = LUID()
    if not advapi32.LookupPrivilegeValueW(None, "SeShutdownPrivilege", ctypes.byref(luid)):
        return False
    tp = TOKEN_PRIVILEGES()
    tp.PrivilegeCount = 1
    tp.Privileges[0].Luid = luid
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
    return bool(advapi32.AdjustTokenPrivileges(h_token, False, ctypes.byref(tp), 0, None, None))


def _windows_power(restart: bool) -> tuple:
    """Force shutdown/restart — can khi man hinh khoa (khong co UI de dong app)."""
    flag = "/r" if restart else "/s"
    verb = "khoi dong lai" if restart else "tat"
    result = subprocess.run(
        ["shutdown", flag, "/t", "5", "/f"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        return True, f"May se {verb} sau 5 giay (force).{_lock_note()}"

    err = (result.stderr or result.stdout or "").strip()
    try:
        import ctypes
        _enable_windows_shutdown_privilege()
        ewx_force = 0x00000004
        ewx_force_hung = 0x00000010
        ewx = (0x00000002 if restart else 0x00000001) | ewx_force | ewx_force_hung
        if ctypes.windll.user32.ExitWindowsEx(ewx, 0):
            return True, f"Da gui ExitWindowsEx de {verb}.{_lock_note()}"
    except Exception:
        pass

    denied = "access" in err.lower() or result.returncode != 0
    hint = (
        " Thieu quyen shutdown. Tren Windows, tai khoan hien tai can quyen "
        "tat may (Local Security Policy / Group Policy). "
        "Khong the bam UAC khi man hinh dang khoa."
    )
    return False, f"Khong the {verb}: {err or result.returncode}.{hint if denied else ''}"


def _macos_power(restart: bool) -> tuple:
    """System Events thuong that bai khi khoa man hinh — fallback loginwindow."""
    verb = "khoi dong lai" if restart else "tat may"
    script = (
        'tell app "System Events" to restart'
        if restart else
        'tell app "System Events" to shut down'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True, timeout=10,
            capture_output=True, text=True,
        )
        return True, f"Da gui lenh {verb} qua System Events.{_lock_note()}"
    except Exception:
        pass

    event = "aevtrsd" if restart else "aevshut"
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "loginwindow" to «event {event}»'],
            check=True, timeout=10,
            capture_output=True, text=True,
        )
        return True, f"Da gui lenh {verb} qua loginwindow (may co the dang khoa).{_lock_note()}"
    except Exception as e:
        return False, (
            f"Khong the {verb} khi man hinh khoa/System Events bi chan: {e}. "
            "Cap quyen Accessibility cho Python, hoac mo khoa man hinh roi thu lai."
        )


def _linux_power(restart: bool) -> tuple:
    verb = "khoi dong lai" if restart else "tat may"
    cmds = (
        [["systemctl", "reboot"], ["loginctl", "reboot"], ["shutdown", "-r", "+0"]]
        if restart else
        [["systemctl", "poweroff"], ["loginctl", "poweroff"], ["shutdown", "-h", "+0"]]
    )
    last_err = None
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, timeout=10, capture_output=True, text=True)
            return True, f"Da gui lenh {verb} ({' '.join(cmd)}).{_lock_note()}"
        except FileNotFoundError as e:
            last_err = e
        except subprocess.CalledProcessError as e:
            last_err = e
    return False, f"Khong the {verb} (thieu quyen?): {last_err}"


def shutdown_now() -> tuple:
    system = _os()
    try:
        if system == "Windows":
            return _windows_power(restart=False)
        if system == "Darwin":
            return _macos_power(restart=False)
        if system == "Linux":
            return _linux_power(restart=False)
        return False, f"He dieu hanh {system} chua duoc ho tro."
    except Exception as e:
        return False, f"Loi khi tat may: {e}"


def restart_now() -> tuple:
    system = _os()
    try:
        if system == "Windows":
            return _windows_power(restart=True)
        if system == "Darwin":
            return _macos_power(restart=True)
        if system == "Linux":
            return _linux_power(restart=True)
        return False, f"He dieu hanh {system} chua duoc ho tro."
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
