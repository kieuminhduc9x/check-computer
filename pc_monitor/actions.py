"""
actions.py - Cac hanh dong dieu khien may tinh: chup man hinh, khoa may,
tat may, khoi dong lai. Code rieng cho tung OS vi day la thao tac he thong,
khong co API chung cho ca 3 OS.
"""

import os
import platform
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from . import config

_screenshot_lock = threading.Lock()


def _os() -> str:
    return platform.system()  # "Windows" | "Darwin" | "Linux"


# --------------------------------- SCREENSHOT --------------------------------

def list_monitors() -> tuple[bool, str]:
    try:
        import mss
        with mss.mss() as sct:
            lines = []
            for i, mon in enumerate(sct.monitors):
                label = "tat ca man hinh" if i == 0 else f"man {i}"
                lines.append(f"{i}: {label} {mon.get('width')}x{mon.get('height')}")
            return True, "Man hinh:\n" + "\n".join(lines) + "\nDung: /screenshot 1 hoac /screenshot all"
    except Exception as e:
        return False, str(e)


def take_screenshot(which: str = "") -> tuple:
    """Chup man hinh ra file tam. which rong = man chinh, all = ghep, so = dung man do."""
    system = _os()
    fd, tmp = tempfile.mkstemp(prefix="pcmon-shot-", suffix=".png")
    os.close(fd)
    path = Path(tmp)
    try:
        import mss
        import mss.tools

        with _screenshot_lock:
            with mss.mss() as sct:
                if len(sct.monitors) < 2 and system != "Windows":
                    path.unlink(missing_ok=True)
                    return False, (
                        "Khong thay man hinh de chup. "
                        "Tren Linux can phien do hoa (X11/Wayland) dang dang nhap. "
                        "Tren macOS can cap Screen Recording cho Python/Terminal."
                    )
                pick = (which or "").strip().lower()
                if pick in ("", "main", "1"):
                    index = 1 if len(sct.monitors) > 1 else 0
                elif pick in ("all", "0", "*"):
                    index = 0
                else:
                    try:
                        index = int(pick)
                    except ValueError:
                        path.unlink(missing_ok=True)
                        return False, "Dung /screenshot, /screenshot 2 hoac /screenshot all"
                    if index < 0 or index >= len(sct.monitors):
                        path.unlink(missing_ok=True)
                        return False, f"Khong co man {index}. Co {len(sct.monitors) - 1} man (1..{len(sct.monitors) - 1})."
                monitor = sct.monitors[index]
                shot = sct.grab(monitor)
                mss.tools.to_png(shot.rgb, shot.size, output=str(path))

        if not path.exists() or path.stat().st_size < 100:
            path.unlink(missing_ok=True)
            return False, "Chup xong nhung file anh rong — co the man hinh dang khoa hoac service khong thay desktop."

        # Telegram sendPhoto gioi han ~10MB; nen anh lon.
        try:
            from PIL import Image
            if path.stat().st_size > 3 * 1024 * 1024:
                img = Image.open(path)
                img = img.convert("RGB")
                jpg_path = path.with_suffix(".jpg")
                img.save(jpg_path, "JPEG", quality=70, optimize=True)
                path.unlink(missing_ok=True)
                path = jpg_path
        except Exception:
            pass
        return True, str(path)
    except Exception as e:
        path.unlink(missing_ok=True)
        hint = ""
        err = str(e).lower()
        if system == "Darwin" or "screen" in err or "permission" in err:
            hint = (
                " Tren macOS: System Settings -> Privacy & Security -> "
                "Screen Recording, bat cho Terminal/Python, roi mo lai listener."
            )
        elif system == "Linux":
            hint = " Tren Linux: can dang nhap desktop (X11/Wayland), khong dung duoc tren server khong man hinh."
        elif system == "Windows":
            hint = (
                " Tren Windows: mo khoa man hinh. Neu bot chay bang Task Scheduler "
                "ma van loi, thu chay tay: python main.py listen trong phien dang nhap."
            )
        return False, f"Khong chup duoc man hinh: {e}.{hint}"


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
    windir = os.environ.get("WINDIR") or r"C:\Windows"
    shutdown_exe = str(Path(windir) / "System32" / "shutdown.exe")
    if not Path(shutdown_exe).exists():
        shutdown_exe = "shutdown.exe"
    result = subprocess.run(
        [shutdown_exe, flag, "/t", "5", "/f"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        return True, f"May se {verb} sau 5 giay (force).{_lock_note()}"

    err = (result.stderr or result.stdout or "").strip()
    try:
        ps_cmd = "Restart-Computer -Force" if restart else "Stop-Computer -Force"
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15,
        )
        if ps.returncode == 0:
            return True, f"Da gui {ps_cmd}.{_lock_note()}"
        err = (err + " | " + (ps.stderr or ps.stdout or "")).strip()
    except Exception:
        pass
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

# --------------------------------- CLOSE APPS --------------------------------

_PROTECTED_NAMES = {
    "Windows": {
        "explorer.exe", "dwm.exe", "sihost.exe", "svchost.exe",
        "searchhost.exe", "startmenuexperiencehost.exe",
        "shellexperiencehost.exe", "textinputhost.exe",
        "applicationframehost.exe", "runtimebroker.exe",
        "securityhealthsystray.exe", "systemsettings.exe",
        "lockapp.exe", "conhost.exe", "csrss.exe", "winlogon.exe",
        "lsass.exe", "services.exe", "fontdrvhost.exe",
        "taskmgr.exe", "ctfmon.exe",
    },
    "Darwin": {
        "finder", "dock", "systemuiserver", "controlcenter",
        "notificationcenter", "windowserver", "loginwindow",
        "spotlight", "siri", "coreaudiod", "system events",
        "wallpaper", "control center", "notification centre",
    },
    "Linux": {
        "gnome-shell", "plasmashell", "kwin_x11", "kwin_wayland",
        "xfce4-session", "xfce4-panel", "cinnamon", "muffin",
        "xdg-desktop-portal", "xdg-desktop-portal-gtk",
        "gsd-xsettings", "nautilus-desktop", "systemd",
    },
}


def _protected_pids() -> set[int]:
    """Listener + terminal dang chay no — khong tat de bot con tra loi."""
    import psutil

    pids = {os.getpid(), os.getppid()}
    try:
        proc = psutil.Process()
        current = proc
        for _ in range(6):
            pids.add(current.pid)
            parent = current.parent()
            if parent is None:
                break
            current = parent
    except Exception:
        pass
    project = str(config.PROJECT_ROOT.resolve()).replace("\\", "/").lower()
    try:
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(str(x) for x in (proc.info.get("cmdline") or []))
            except Exception:
                continue
            low = cmd.replace("\\", "/").lower()
            if "main.py" in low and "listen" in low and project in low:
                pids.add(int(proc.info["pid"]))
    except Exception:
        pass
    return pids


def _windows_close_windows(pids: set[int]) -> int:
    """Gui WM_CLOSE toi cua so visible cua pid (giong bam X), khong TerminateProcess ngay."""
    if not pids:
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    sent = 0
    target = set(pids)
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, lparam):
        nonlocal sent
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in target:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                sent += 1
        except Exception:
            return True
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    return sent


def _windows_taskkill(pids: list[int]) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                timeout=8,
                capture_output=True,
                creationflags=flags,
            )
        except Exception:
            continue


def _is_protected_app(name: str) -> bool:
    key = (name or "").strip().lower()
    if not key:
        return True
    protected = _PROTECTED_NAMES.get(_os(), set())
    if key in protected:
        return True
    if key in ("python", "python.exe", "pythonw", "pythonw.exe", "python3", "python3.exe"):
        return True
    return False


def _macos_quit_app(name: str) -> bool:
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{escaped}" to quit'],
            timeout=8, capture_output=True, text=True,
        )
        return True
    except Exception:
        return False


def close_all_apps() -> tuple:
    """Tat cac ung dung giao dien dang mo. Giu desktop, listener, terminal cua bot."""
    try:
        from . import system_info
        return _close_app_entries(system_info.get_running_apps(), closing_all=True)
    except Exception as e:
        return False, f"Loi khi tat ung dung: {e}"


def close_one_app(query: str) -> tuple[bool, str, list[dict]]:
    """Tat 1 app dang mo. hits khac rong khi nhieu app khop."""
    from . import system_info

    q = (query or "").strip()
    if not q:
        return False, "Gui /close tenapp. Vi du /close chrome", []
    status, item, hits = system_info.match_running_app(q)
    if status == "none":
        return False, f"Khong thay app dang mo khop '{q}'. Gui /apps de xem danh sach.", []
    if status == "many":
        names = ", ".join(str(a.get("name") or "?") for a in hits)
        return False, f"Nhieu app khop: {names}. Bam nut hoac ghi ro hon.", hits
    name = str((item or {}).get("name") or "")
    if _is_protected_app(name):
        return False, f"Khong tat {name} (desktop / listener / tien trinh he thong).", []
    ok, msg = _close_app_entries([item or {}], closing_all=False)
    return ok, msg, []


def _close_app_entries(apps: list[dict], closing_all: bool) -> tuple:
    import psutil

    keep = _protected_pids()
    closed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    seen_pids: set[int] = set()
    system = _os()

    if not apps:
        return True, "Khong thay ung dung giao dien nao de tat."

    for app in apps:
        name = str(app.get("name") or "").strip()
        if _is_protected_app(name):
            skipped.append(name)
            continue
        pids = [int(p) for p in (app.get("pids") or []) if p]
        if not pids:
            try:
                for proc in psutil.process_iter(["pid", "name"]):
                    pname = (proc.info.get("name") or "")
                    if pname == name or pname.lower() == name.lower():
                        pids.append(int(proc.info["pid"]))
            except Exception:
                pass
        pids = [p for p in pids if p not in keep and p not in seen_pids]
        if not pids and system != "Darwin":
            skipped.append(name or "?")
            continue

        ok = False
        if system == "Darwin":
            ok = _macos_quit_app(name)
        elif system == "Windows":
            _windows_close_windows(set(pids))
            ok = True
        for pid in pids:
            seen_pids.add(pid)
            if system == "Windows":
                continue
            try:
                proc = psutil.Process(pid)
                if proc.pid in keep:
                    continue
                proc.terminate()
                ok = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if ok:
            closed.append(name)
        else:
            failed.append(name)

    if system == "Windows" and seen_pids:
        time.sleep(2)
        still = []
        for pid in list(seen_pids):
            try:
                if psutil.pid_exists(pid) and pid not in keep:
                    still.append(pid)
            except Exception:
                continue
        if still:
            _windows_taskkill(still)
            time.sleep(1)

    if seen_pids and system != "Windows":
        waiting = []
        for pid in seen_pids:
            try:
                waiting.append(psutil.Process(pid))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if waiting:
            _gone, alive = psutil.wait_procs(waiting, timeout=2)
            for proc in alive:
                if proc.pid in keep:
                    continue
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

    still_open = []
    if system == "Windows":
        for pid in seen_pids:
            try:
                if psutil.pid_exists(pid) and pid not in keep:
                    proc = psutil.Process(pid)
                    still_open.append(proc.name())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if not closed and not failed:
        return True, (
            "Khong tat app nao (chi con desktop / listener). "
            + (f"Bo qua: {', '.join(skipped[:8])}." if skipped else "")
        )

    if closing_all:
        lines = [f"Da gui lenh tat {len(closed)} ung dung."]
    else:
        lines = [f"Da tat {closed[0]}." if closed else "Khong tat duoc app."]
    if closing_all and closed:
        lines.append(", ".join(closed[:20]) + ("…" if len(closed) > 20 else ""))
    if skipped:
        lines.append("Giu lai: " + ", ".join(skipped[:8]))
    if failed:
        lines.append("Khong tat duoc: " + ", ".join(failed[:8]))
    if still_open:
        lines.append("Van song: " + ", ".join(sorted(set(still_open))[:8]))
    return True, "\n".join(lines)


def append_note(text: str) -> tuple:
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(config.NOTE_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")
        return True, f"Da luu ghi chu vao {config.NOTE_FILE.name}"
    except Exception as e:
        return False, f"Khong luu duoc ghi chu: {e}"
