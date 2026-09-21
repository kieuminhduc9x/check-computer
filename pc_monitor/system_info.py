"""
system_info.py - Lay thong tin he thong theo cach cross-platform
(Windows / macOS / Linux) bang psutil, khong can code rieng cho tung OS.
"""

from __future__ import annotations

import os
import re
import socket
import time
import platform
import subprocess
from datetime import datetime, timedelta

import psutil
import requests


def _html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _os_name() -> str:
    return platform.system()  # "Windows" | "Darwin" | "Linux"


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "khong xac dinh"


def get_public_ip() -> str:
    try:
        resp = requests.get("https://api.ipify.org", timeout=5)
        if resp.status_code == 200:
            return resp.text.strip()
        return "khong lay duoc"
    except Exception:
        return "khong lay duoc (co the mang chan)"


def get_uptime_str() -> str:
    """Uptime tinh theo psutil.boot_time(), hoat dong tren ca 3 OS."""
    try:
        boot_ts = psutil.boot_time()
        seconds = time.time() - boot_ts
        delta = timedelta(seconds=seconds)
        total_minutes = int(delta.total_seconds() // 60)
        hours, minutes = divmod(total_minutes, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days:
            parts.append(f"{days} ngay")
        if hours:
            parts.append(f"{hours} gio")
        parts.append(f"{minutes} phut")
        return " ".join(parts)
    except Exception:
        return "khong xac dinh"


def get_os_label() -> str:
    system = _os_name()
    if system == "Darwin":
        mac_ver = platform.mac_ver()[0] or "?"
        return f"macOS {mac_ver} ({platform.machine()})"
    if system == "Windows":
        return f"Windows {platform.release()} ({platform.machine()})"
    if system == "Linux":
        dist = ""
        try:
            rel = platform.freedesktop_os_release()
            dist = rel.get("PRETTY_NAME") or rel.get("NAME") or ""
        except Exception:
            dist = ""
        return dist or f"Linux {platform.release()} ({platform.machine()})"
    return f"{system} {platform.release()}"


def get_battery_text() -> str | None:
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None
    if battery is None:
        return None
    plugged = "dang sac" if battery.power_plugged else "dung pin"
    return f"{battery.percent:.0f}% ({plugged})"


def _idle_seconds_windows() -> float | None:
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return max(0.0, millis / 1000.0)


def _idle_seconds_macos() -> float | None:
    result = subprocess.run(
        ["ioreg", "-n", "IOHIDSystem", "-r", "-k", "HIDIdleTime"],
        check=True, timeout=8, capture_output=True, text=True,
    )
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', result.stdout)
    if not match:
        return None
    return int(match.group(1)) / 1_000_000_000


def _idle_seconds_linux() -> float | None:
    try:
        result = subprocess.run(
            ["xprintidle"],
            check=True, timeout=5, capture_output=True, text=True,
        )
        return int(result.stdout.strip()) / 1000.0
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return None


def get_idle_seconds() -> float | None:
    try:
        system = _os_name()
        if system == "Windows":
            return _idle_seconds_windows()
        if system == "Darwin":
            return _idle_seconds_macos()
        if system == "Linux":
            return _idle_seconds_linux()
    except Exception:
        return None
    return None


def format_idle(seconds: float | None) -> str:
    if seconds is None:
        return "khong xac dinh"
    total = int(seconds)
    if total < 15:
        return "dang dung"
    if total < 60:
        return f"{total} giay truoc"
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} gio {minutes} phut truoc"
    return f"{minutes} phut truoc"


def _is_locked_windows() -> bool | None:
    import ctypes

    user32 = ctypes.windll.user32
    desktop = user32.OpenInputDesktop(0, False, 0)
    if desktop:
        user32.CloseDesktop(desktop)
        return False
    # OpenInputDesktop that fail thuong nghia man hinh dang khoa / session khac
    hdesk = user32.OpenDesktopW("Default", 0, False, 0x0100)
    if not hdesk:
        return None
    switched = user32.SwitchDesktop(hdesk)
    user32.CloseDesktop(hdesk)
    return not bool(switched)


def _is_locked_macos() -> bool | None:
    try:
        saver = subprocess.run(
            ["pgrep", "-x", "ScreenSaverEngine"],
            timeout=5, capture_output=True,
        )
        if saver.returncode == 0:
            return True
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first application process whose frontmost is true'],
            timeout=8, capture_output=True, text=True,
        )
        name = (result.stdout or "").strip()
        if name in ("loginwindow", "ScreenSaverEngine"):
            return True
        if name:
            return False
    except Exception:
        pass
    return None


def _is_locked_linux() -> bool | None:
    session = os.environ.get("XDG_SESSION_ID")
    if not session:
        return None
    try:
        result = subprocess.run(
            ["loginctl", "show-session", session, "-p", "LockedHint"],
            check=True, timeout=5, capture_output=True, text=True,
        )
        line = (result.stdout or "").strip().lower()
        if line.endswith("=yes"):
            return True
        if line.endswith("=no"):
            return False
    except Exception:
        return None
    return None


def is_screen_locked() -> bool | None:
    try:
        system = _os_name()
        if system == "Windows":
            return _is_locked_windows()
        if system == "Darwin":
            return _is_locked_macos()
        if system == "Linux":
            return _is_locked_linux()
    except Exception:
        return None
    return None


def format_lock_state(locked: bool | None) -> str:
    if locked is True:
        return "dang khoa"
    if locked is False:
        return "dang mo"
    return "khong xac dinh"


def get_cpu_text() -> str:
    percent = psutil.cpu_percent(interval=1)
    freq = psutil.cpu_freq()
    freq_str = f"{freq.current:.0f} MHz" if freq else "khong xac dinh"
    cores = psutil.cpu_count(logical=False) or "?"
    threads = psutil.cpu_count(logical=True) or "?"
    return (
        f"🖥️ <b>CPU</b>\n"
        f"Su dung: {percent}%\n"
        f"Toc do: {freq_str}\n"
        f"So nhan/luong: {cores}/{threads}"
    )


def get_ram_text() -> str:
    mem = psutil.virtual_memory()
    used_gb = mem.used / (1024 ** 3)
    total_gb = mem.total / (1024 ** 3)
    return (
        f"🧠 <b>RAM</b>\n"
        f"Su dung: {mem.percent}%\n"
        f"Da dung: {used_gb:.1f} GB / {total_gb:.1f} GB"
    )


def get_disk_text() -> str:
    lines = ["💾 <b>O DIA</b>"]
    partitions = psutil.disk_partitions(all=False)
    seen = set()
    for p in partitions:
        if p.device in seen:
            continue
        seen.add(p.device)
        try:
            usage = psutil.disk_usage(p.mountpoint)
        except (PermissionError, OSError):
            continue
        used_gb = usage.used / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        lines.append(
            f"{p.mountpoint}: {usage.percent}% "
            f"({used_gb:.1f} GB / {total_gb:.1f} GB)"
        )
    return "\n".join(lines)


def get_top_processes_text(limit: int = 5) -> str:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Lay cpu_percent lan 2 cho chinh xac hon (lan dau psutil tra ve 0.0)
    psutil.cpu_percent(interval=0.5, percpu=False)
    for p in procs:
        try:
            proc = psutil.Process(p["pid"])
            p["cpu_percent"] = proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            p["cpu_percent"] = 0.0

    top_cpu = sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:limit]

    lines = [f"⚙️ <b>TOP {limit} TIEN TRINH (theo CPU)</b>"]
    for p in top_cpu:
        lines.append(
            f"- {p.get('name', '?')} (PID {p.get('pid')}): "
            f"CPU {p.get('cpu_percent', 0):.1f}%, RAM {p.get('memory_percent', 0):.1f}%"
        )
    return "\n".join(lines)


def _get_foreground_windows() -> tuple[str | None, str | None]:
    """Tra ve (ten ung dung, tieu de cua so dang focus)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, None
    length = user32.GetWindowTextLengthW(hwnd)
    title = None
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip() or None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    app_name = None
    try:
        app_name = psutil.Process(pid.value).name()
    except Exception:
        app_name = title
    return app_name, title


def _get_visible_apps_windows() -> list:
    """Danh sach ung dung dang hien thi, gom theo process + cua so (Windows)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080

    fg_app, fg_title = _get_foreground_windows()
    grouped = {}

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app_name = title
        try:
            app_name = psutil.Process(pid.value).name() or title
        except Exception:
            pass
        entry = grouped.setdefault(app_name, {"name": app_name, "frontmost": False, "windows": []})
        if title not in entry["windows"]:
            entry["windows"].append(title)
        if fg_app and app_name == fg_app:
            entry["frontmost"] = True
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    apps = list(grouped.values())
    if fg_app and fg_app not in grouped:
        apps.append({
            "name": fg_app,
            "frontmost": True,
            "windows": [fg_title] if fg_title else [],
        })
    return apps


def _macos_front_windows(app_name: str) -> list:
    """Lay tieu de cua so cua app dang focus — 1 process nen thuong rat nhanh."""
    if not app_name:
        return []
    escaped = app_name.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "System Events"
    try
        set wins to name of windows of (first process whose name is "{escaped}")
        set AppleScript's text item delimiters to linefeed
        set out to wins as text
        set AppleScript's text item delimiters to ""
        return out
    on error
        return ""
    end try
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            timeout=3, capture_output=True, text=True,
        )
        if result.returncode != 0:
            return []
        return [n.strip() for n in result.stdout.splitlines() if n.strip()]
    except Exception:
        return []


def _get_visible_apps_macos() -> list:
    """Ung dung co giao dien + app dang focus (macOS)."""
    script = r'''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    set appNames to name of every process whose background only is false
    set AppleScript's text item delimiters to linefeed
    set nameStr to appNames as text
    set AppleScript's text item delimiters to ""
    return "FRONT:" & frontApp & linefeed & nameStr
end tell
'''
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True, timeout=8, capture_output=True, text=True,
    )
    names = []
    front = None
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("FRONT:"):
            front = line[6:].strip()
            continue
        names.append(line)
    if front and front not in names:
        names.insert(0, front)

    windows = _macos_front_windows(front) if front else []
    apps = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        apps.append({
            "name": name,
            "frontmost": bool(front and name == front),
            "windows": windows if name == front else [],
        })
    return apps


def _get_visible_apps_linux() -> list:
    """Cua so dang hien thi (Linux), uu tien wmctrl, fallback xdotool."""
    grouped = {}
    front_title = None
    try:
        active = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            timeout=5, capture_output=True, text=True,
        )
        if active.returncode == 0:
            front_title = active.stdout.strip() or None
    except FileNotFoundError:
        front_title = None

    result = subprocess.run(
        ["wmctrl", "-lp"], check=True, timeout=10, capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid_s, title = parts[2], parts[4].strip()
        if not title:
            continue
        app_name = title
        try:
            app_name = psutil.Process(int(pid_s)).name() or title
        except Exception:
            pass
        entry = grouped.setdefault(app_name, {"name": app_name, "frontmost": False, "windows": []})
        if title not in entry["windows"]:
            entry["windows"].append(title)
        if front_title and title == front_title:
            entry["frontmost"] = True
    return list(grouped.values())


def get_running_apps() -> list:
    """Tra ve list dict: {name, frontmost, windows}. Rong neu khong lay duoc UI."""
    system = _os_name()
    try:
        if system == "Windows":
            apps = _get_visible_apps_windows()
        elif system == "Darwin":
            apps = _get_visible_apps_macos()
        elif system == "Linux":
            apps = _get_visible_apps_linux()
        else:
            apps = []
    except Exception:
        apps = []

    apps = [a for a in apps if a.get("name")]
    apps.sort(key=lambda a: (not a.get("frontmost"), a["name"].lower()))
    return apps


def get_foreground_app_name(apps: list | None = None) -> str | None:
    if apps is None:
        apps = get_running_apps()
    for app in apps:
        if app.get("frontmost"):
            return app.get("name")
    return None


def _format_apps_lines(apps: list, limit: int = 40, windows_per_app: int = 4) -> list:
    lines = []
    shown = apps[:limit]
    for app in shown:
        mark = "★ " if app.get("frontmost") else "- "
        name = _html_escape(app.get("name") or "?")
        extra = " (dang dung)" if app.get("frontmost") else ""
        lines.append(f"{mark}{name}{extra}")
        windows = [w for w in (app.get("windows") or []) if w and w != app.get("name")]
        for win in windows[:windows_per_app]:
            lines.append(f"    · {_html_escape(win)}")
        if len(windows) > windows_per_app:
            lines.append(f"    · ... va {len(windows) - windows_per_app} cua so khac")
    if len(apps) > limit:
        lines.append(f"... va {len(apps) - limit} ung dung khac")
    return lines


def get_running_apps_text(limit: int = 40) -> str:
    """Uu tien liet ke ung dung co giao dien dang mo (giong 'Task View').
    Neu khong lay duoc (server khong man hinh, thieu cong cu...), fallback
    sang liet ke theo ten tien trinh gop nhom (khong phan biet co UI hay khong)."""
    apps = get_running_apps()
    if apps:
        lines = [f"📱 <b>UNG DUNG DANG MO</b> ({len(apps)})"]
        fg = get_foreground_app_name(apps)
        if fg:
            lines.append(f"Dang dung: {_html_escape(fg)}")
        lines.extend(_format_apps_lines(apps, limit=limit))
        return "\n".join(lines)

    counts = {}
    try:
        iterator = psutil.process_iter(["name"])
        for p in iterator:
            try:
                name = p.info.get("name") or "?"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            counts[name] = counts.get(name, 0) + 1
    except (psutil.AccessDenied, PermissionError):
        return (
            "📱 <b>UNG DUNG DANG MO</b>\n"
            "Khong du quyen de doc danh sach ung dung / tien trinh."
        )

    sorted_names = sorted(counts.items(), key=lambda x: x[0].lower())
    lines = [
        "📱 <b>DANH SACH TIEN TRINH</b>",
        "(khong lay duoc danh sach giao dien — fallback tien trinh he thong)",
    ]
    for name, count in sorted_names[:limit]:
        suffix = f" x{count}" if count > 1 else ""
        lines.append(f"- {_html_escape(name)}{suffix}")
    if len(sorted_names) > limit:
        lines.append(f"... va {len(sorted_names) - limit} tien trinh khac")
    return "\n".join(lines)


def get_disk_summary_text() -> str:
    parts = []
    seen = set()
    for p in psutil.disk_partitions(all=False):
        if p.device in seen:
            continue
        seen.add(p.device)
        try:
            usage = psutil.disk_usage(p.mountpoint)
        except (PermissionError, OSError):
            continue
        mount = p.mountpoint
        fstype = (p.fstype or "").lower()
        if fstype in {"devfs", "autofs", "tmpfs"}:
            continue
        if mount.startswith("/private/"):
            continue
        if mount.startswith("/System/Volumes/") and mount != "/System/Volumes/Data":
            continue
        parts.append(f"{mount} {usage.percent:.0f}%")
        if len(parts) >= 3:
            break
    return ", ".join(parts) if parts else "khong xac dinh"


def get_status_overview_text(computer_name: str | None = None) -> str:
    """Snapshot 1 man: may dang bat, tai nguyen, app dang dung, app dang mo."""
    now_str = datetime.now().strftime("%H:%M:%S ngay %d/%m/%Y")
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.4)
    apps = get_running_apps()
    fg = get_foreground_app_name(apps)
    locked = is_screen_locked()
    idle = format_idle(get_idle_seconds())
    battery = get_battery_text()
    host = get_hostname()
    label = computer_name or host
    display = label if label == host else f"{label} ({host})"

    lines = [
        "🟢 <b>MAY TINH DANG BAT</b>",
        f"Ten may: {_html_escape(display)}",
        f"He dieu hanh: {_html_escape(get_os_label())}",
        f"IP noi bo: {get_local_ip()}",
        f"Da bat lien tuc: {get_uptime_str()}",
        f"Man hinh: {format_lock_state(locked)}",
        f"Khong thao tac: {idle}",
    ]
    if battery:
        lines.append(f"Pin: {battery}")
    lines.extend([
        f"CPU: {cpu:.0f}%",
        f"RAM: {mem.percent:.0f}% ({mem.used / (1024 ** 3):.1f} / {mem.total / (1024 ** 3):.1f} GB)",
        f"O dia: {get_disk_summary_text()}",
        f"Thoi gian kiem tra: {now_str}",
        "",
        f"Dang dung: {_html_escape(fg)}" if fg else "Dang dung: khong xac dinh",
    ])

    if apps:
        lines.append(f"Ung dung dang mo ({len(apps)}):")
        lines.extend(_format_apps_lines(apps, limit=12, windows_per_app=2))
        if len(apps) > 12:
            lines.append("Gui /apps de xem day du.")
    else:
        lines.append("Khong lay duoc danh sach ung dung giao dien.")
        lines.append("Gui /apps de xem danh sach tien trinh.")

    return "\n".join(lines)


def get_cpu_ram_percent() -> tuple:
    """Dung rieng cho vong lap canh bao (khong format text)."""
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    return cpu, ram


def get_hostname() -> str:
    return platform.node()
