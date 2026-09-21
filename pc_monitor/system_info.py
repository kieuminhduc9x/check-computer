"""
system_info.py - Lay thong tin he thong theo cach cross-platform
(Windows / macOS / Linux) bang psutil, khong can code rieng cho tung OS.
"""

import socket
import platform
import ctypes
from datetime import timedelta

import psutil
import requests


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
        import time
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


def _get_visible_apps_windows() -> list:
    """Danh sach ten cua so dang hien thi (Windows), vd: 'Chrome', 'Notepad'."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            app_name = title
            try:
                app_name = psutil.Process(pid.value).name()
            except Exception:
                pass
            titles.append(f"{title} ({app_name})")
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    return titles


def _get_visible_apps_macos() -> list:
    """Danh sach ung dung dang co giao dien (khong chay nen), macOS."""
    import subprocess
    script = (
        'tell application "System Events" to get name of every process '
        'whose background only is false'
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True, timeout=10, capture_output=True, text=True,
    )
    names = [n.strip() for n in result.stdout.split(",") if n.strip()]
    return names


def _get_visible_apps_linux() -> list:
    """Danh sach cua so dang hien thi (Linux), can co lenh wmctrl."""
    import subprocess
    result = subprocess.run(
        ["wmctrl", "-l"], check=True, timeout=10, capture_output=True, text=True,
    )
    apps = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            apps.append(parts[3].strip())
    return apps


def get_running_apps_text(limit: int = 40) -> str:
    """Uu tien liet ke ung dung co giao dien dang mo (giong 'Task View').
    Neu khong lay duoc (server khong man hinh, thieu cong cu...), fallback
    sang liet ke theo ten tien trinh gop nhom (khong phan biet co UI hay khong)."""
    system = platform.system()
    apps = []
    method = "giao dien"

    try:
        if system == "Windows":
            apps = _get_visible_apps_windows()
        elif system == "Darwin":
            apps = _get_visible_apps_macos()
        elif system == "Linux":
            apps = _get_visible_apps_linux()
    except Exception:
        apps = []

    if apps:
        apps = sorted(set(apps), key=str.lower)
        lines = [f"📱 <b>UNG DUNG DANG MO</b> ({len(apps)})"]
        for a in apps[:limit]:
            lines.append(f"- {a}")
        if len(apps) > limit:
            lines.append(f"... va {len(apps) - limit} ung dung khac")
        return "\n".join(lines)

    # --- Fallback: gop nhom tien trinh theo ten (khong phan biet co UI) ---
    method = "tien trinh he thong (khong lay duoc danh sach giao dien)"
    counts = {}
    for p in psutil.process_iter(["name"]):
        try:
            name = p.info.get("name") or "?"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        counts[name] = counts.get(name, 0) + 1

    sorted_names = sorted(counts.items(), key=lambda x: x[0].lower())
    lines = [f"📱 <b>DANH SACH TIEN TRINH</b> (fallback - {method})"]
    for name, count in sorted_names[:limit]:
        suffix = f" x{count}" if count > 1 else ""
        lines.append(f"- {name}{suffix}")
    if len(sorted_names) > limit:
        lines.append(f"... va {len(sorted_names) - limit} tien trinh khac")
    return "\n".join(lines)


def get_cpu_ram_percent() -> tuple:
    """Dung rieng cho vong lap canh bao (khong format text)."""
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    return cpu, ram


def get_hostname() -> str:
    return platform.node()
