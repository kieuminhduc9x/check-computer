"""
autostart.py - Dang ky / go bo service tu khoi dong (cross-platform).

macOS : launchd LaunchAgents
Linux : systemd --user
Windows: Task Scheduler (schtasks, tai khoan nguoi dung hien tai)
"""

from __future__ import annotations

import os
import sys
import json
import time
import signal
import platform
import subprocess
from pathlib import Path

from . import config

ROLE_ENV = "PCMONITOR_ROLE"
LISTENER_ROLE = "listener"

MAC_LABELS = ("startup", "heartbeat", "listener")
LINUX_UNITS = (
    "pcmonitor-startup.service",
    "pcmonitor-listener.service",
    "pcmonitor-heartbeat.service",
    "pcmonitor-heartbeat.timer",
)
WIN_TASKS = (
    "PCMonitorPro_Startup",
    "PCMonitorPro_Listener",
    "PCMonitorPro_Heartbeat",
)
WIN_STARTUP_CMDS = (
    "PCMonitorPro_Startup.cmd",
    "PCMonitorPro_Listener.vbs",
    "PCMonitorPro_Listener.cmd",
)


def running_as_listener() -> bool:
    return os.environ.get(ROLE_ENV) == LISTENER_ROLE


def mark_listener_role() -> None:
    os.environ[ROLE_ENV] = LISTENER_ROLE


def _python_bin() -> str:
    return str(Path(sys.executable).resolve())


def _project_dir() -> Path:
    return config.PROJECT_ROOT


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    extra: dict = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": kwargs.pop("timeout", 30),
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    extra.update(kwargs)
    return subprocess.run(cmd, **extra)


def _fill_template(template: Path, dest: Path, mapping: dict[str, str]) -> None:
    text = template.read_text(encoding="utf-8")
    for key, value in mapping.items():
        text = text.replace(key, value)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def _mapping() -> dict[str, str]:
    python_bin = _python_bin()
    project = str(_project_dir())
    minutes = max(1, int(config.HEARTBEAT_MINUTES))
    return {
        "__PYTHON_BIN__": python_bin,
        "__PROJECT_DIR__": project,
        "__HEARTBEAT_SECONDS__": str(minutes * 60),
        "__HEARTBEAT_MINUTES__": str(minutes),
    }


def _os() -> str:
    return platform.system()


# ---------------------------------- macOS ------------------------------------

def _macos_plist_path(name: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.pcmonitor.{name}.plist"


def _macos_launchctl(args: list[str]) -> subprocess.CompletedProcess:
    return _run(["launchctl", *args])


def _macos_uid_domain() -> tuple[int, str]:
    uid = os.getuid()
    return uid, f"gui/{uid}"


def _macos_enable(name: str) -> None:
    _, domain = _macos_uid_domain()
    _macos_launchctl(["enable", f"{domain}/com.pcmonitor.{name}"])


def _install_macos(*, start_listener_now: bool) -> tuple[bool, str]:
    mapping = _mapping()
    templates = _project_dir() / "scripts" / "macos"
    lines = ["Da dang ky launchd (chay khi dang nhap, khong can go listen):"]
    _, domain = _macos_uid_domain()
    for name in MAC_LABELS:
        template = templates / f"com.pcmonitor.{name}.plist.template"
        dest = _macos_plist_path(name)
        if not template.exists():
            return False, f"Thieu template: {template}"
        _fill_template(template, dest, mapping)
        _macos_enable(name)

        skip_reload = running_as_listener() and not start_listener_now and name in ("listener", "startup")
        if skip_reload:
            lines.append(f"- com.pcmonitor.{name}: da ghi + enable, lan sau dang nhap se tu chay")
            continue

        _macos_launchctl(["bootout", domain, str(dest)])
        _macos_launchctl(["unload", str(dest)])
        loaded = _macos_launchctl(["bootstrap", domain, str(dest)])
        if loaded.returncode != 0:
            loaded = _macos_launchctl(["load", "-w", str(dest)])
        if loaded.returncode != 0:
            err = (loaded.stderr or loaded.stdout or "").strip()
            # "already bootstrapped" van OK
            if "already" not in (err or "").lower():
                return False, f"launchctl {name} that bai: {err or loaded.returncode}"
        _macos_enable(name)
        if name == "listener" and start_listener_now:
            _macos_launchctl(["kickstart", "-k", f"{domain}/com.pcmonitor.listener"])
        lines.append(f"- com.pcmonitor.{name}: OK")
    lines.append("Lan sau CHI CAN DANG NHAP — khong can chay python main.py listen.")
    lines.append("Kiem tra: launchctl list | grep pcmonitor")
    return True, "\n".join(lines)


def _uninstall_macos() -> tuple[bool, str]:
    lines = ["Da go launchd:"]
    for name in MAC_LABELS:
        dest = _macos_plist_path(name)
        skip_unload = name == "listener" and running_as_listener()
        if dest.exists() and not skip_unload:
            _macos_launchctl(["unload", str(dest)])
        if dest.exists():
            dest.unlink()
            extra = " (listener van chay den khi tat process)" if skip_unload else ""
            lines.append(f"- com.pcmonitor.{name}: da xoa{extra}")
        else:
            lines.append(f"- com.pcmonitor.{name}: khong co")
    return True, "\n".join(lines)


def _html(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _status_macos() -> str:
    _, domain = _macos_uid_domain()
    lines = ["macOS launchd:"]
    for name in MAC_LABELS:
        label = f"com.pcmonitor.{name}"
        dest = _macos_plist_path(name)
        printed = _macos_launchctl(["print", f"{domain}/{label}"])
        loaded = printed.returncode == 0
        state = []
        if loaded:
            state.append("dang nap")
        if dest.exists():
            state.append("co file")
        else:
            state.append("chua dang ky")
        lines.append(f"- {label}: {', '.join(state)}")
    return "\n".join(lines)


# ---------------------------------- Linux ------------------------------------

def _linux_unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _systemctl(args: list[str]) -> subprocess.CompletedProcess:
    return _run(["systemctl", "--user", *args])


def _install_linux(*, start_listener_now: bool) -> tuple[bool, str]:
    mapping = _mapping()
    templates = _project_dir() / "scripts" / "linux"
    dest_dir = _linux_unit_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    for unit in LINUX_UNITS:
        template = templates / f"{unit}.template"
        if not template.exists():
            return False, f"Thieu template: {template}"
        _fill_template(template, dest_dir / unit, mapping)

    reloaded = _systemctl(["daemon-reload"])
    if reloaded.returncode != 0:
        err = (reloaded.stderr or reloaded.stdout or "").strip()
        return False, f"systemctl daemon-reload that bai: {err or reloaded.returncode}"

    from_listener = running_as_listener() and not start_listener_now
    enable_cmds = [
        ["enable", "pcmonitor-startup.service"] if from_listener else ["enable", "--now", "pcmonitor-startup.service"],
        ["enable", "--now", "pcmonitor-heartbeat.timer"],
        ["enable", "pcmonitor-listener.service"] if from_listener else ["enable", "--now", "pcmonitor-listener.service"],
    ]

    lines = ["Da dang ky systemd --user (chay khi dang nhap):"]
    for cmd in enable_cmds:
        result = _systemctl(cmd)
        unit = cmd[-1]
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            return False, f"systemctl {' '.join(cmd)} that bai: {err or result.returncode}"
        extra = " (enable, khong start lai process dang chay)" if from_listener and unit.endswith("listener.service") else ""
        lines.append(f"- {unit}: OK{extra}")
    lines.append("Lan sau CHI CAN DANG NHAP — khong can chay python main.py listen.")
    lines.append("Kiem tra: systemctl --user status pcmonitor-listener.service")
    lines.append("Neu can chay ca khi chua dang nhap: sudo loginctl enable-linger $USER")
    return True, "\n".join(lines)


def _uninstall_linux() -> tuple[bool, str]:
    lines = ["Da go systemd --user:"]
    actions = [
        (["disable", "--now", "pcmonitor-startup.service"], "pcmonitor-startup.service"),
        (["disable", "--now", "pcmonitor-heartbeat.timer"], "pcmonitor-heartbeat.timer"),
        (["disable", "--now", "pcmonitor-heartbeat.service"], "pcmonitor-heartbeat.service"),
    ]
    if running_as_listener():
        actions.append((["disable", "pcmonitor-listener.service"], "pcmonitor-listener.service"))
    else:
        actions.append((["disable", "--now", "pcmonitor-listener.service"], "pcmonitor-listener.service"))

    for cmd, unit in actions:
        _systemctl(cmd)
        lines.append(f"- {unit}: da disable")

    dest_dir = _linux_unit_dir()
    for unit in LINUX_UNITS:
        path = dest_dir / unit
        if path.exists():
            path.unlink()
    _systemctl(["daemon-reload"])
    if running_as_listener():
        lines.append("Listener hien tai van chay den khi tat process.")
    return True, "\n".join(lines)


def _status_linux() -> str:
    lines = ["Linux systemd --user:"]
    for unit in ("pcmonitor-listener.service", "pcmonitor-startup.service", "pcmonitor-heartbeat.timer"):
        result = _systemctl(["is-enabled", unit])
        enabled = (result.stdout or "").strip() or "disabled"
        active = _systemctl(["is-active", unit])
        running = (active.stdout or "").strip() or "inactive"
        lines.append(f"- {unit}: {enabled}, {running}")
    return "\n".join(lines)


# --------------------------------- Windows -----------------------------------

def _win_python() -> str:
    """Uu tien python.exe that, tranh stub WindowsApps (Task Scheduler hay im)."""
    exe = Path(_python_bin()).resolve()
    text = str(exe)
    if "WindowsApps" in text:
        finder = _run(["py", "-3", "-c", "import sys; print(sys.executable)"])
        found = (finder.stdout or "").strip()
        if finder.returncode == 0 and found and "WindowsApps" not in found:
            return found
    return str(exe)


def _win_autostart_dir() -> Path:
    path = _project_dir() / ".autostart"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _win_pythonw() -> str:
    exe = Path(_win_python())
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else exe)


def _win_short_path(path: Path | str) -> str:
    """Duong dan 8.3 ASCII neu co — VBScript khong doc UTF-8 / tieng Viet."""
    raw = str(Path(path).resolve())
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(520)
        n = ctypes.windll.kernel32.GetShortPathNameW(raw, buf, 520)
        if n and buf.value and all(ord(c) < 128 for c in buf.value):
            return buf.value
    except Exception:
        pass
    return raw


def _vbs_quote(text: str) -> str:
    return text.replace('"', '""')


def _write_vbs(path: Path, content: str) -> None:
    # WSH chi an toan voi UTF-16 LE + BOM. UTF-8 BOM = 800A0408 Invalid character.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-16")


def _win_write_listen_vbs() -> Path:
    """Chay listener an, khong mo cua so CMD (tranh bi tat nham luc dang nhap)."""
    dest = _win_autostart_dir() / "listen.vbs"
    pythonw = _vbs_quote(_win_short_path(_win_pythonw()))
    main_py = _vbs_quote(_win_short_path(_project_dir() / "main.py"))
    project = _vbs_quote(_win_short_path(_project_dir()))
    _write_vbs(
        dest,
        "On Error Resume Next\r\n"
        "Set sh = CreateObject(\"WScript.Shell\")\r\n"
        f"sh.CurrentDirectory = \"{project}\"\r\n"
        f"sh.Run \"\"\"{pythonw}\"\" -u \"\"{main_py}\"\" listen\", 0, False\r\n",
    )
    return dest


def refresh_windows_startup() -> str:
    """Ghi lai Startup theo thu muc hien tai, xoa .cmd listen (popup CMD / Run)."""
    if _os() != "Windows":
        return ""
    dest_dir = _win_startup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    removed = []
    for name in ("PCMonitorPro_Listener.cmd", "PCMonitorPro_Listener.bat"):
        old = dest_dir / name
        if old.exists():
            old.unlink()
            removed.append(name)
    vbs = _win_write_listen_vbs()
    dest = dest_dir / "PCMonitorPro_Listener.vbs"
    dest.write_bytes(vbs.read_bytes())
    try:
        _run(
            [
                "powershell", "-NoProfile", "-Command",
                f"Unblock-File -LiteralPath {json.dumps(str(dest))}",
            ],
            timeout=5,
        )
    except Exception:
        pass
    extra = f" Da xoa popup: {', '.join(removed)}." if removed else ""
    return f"Da cap nhat Startup an -> {dest}.{extra}"


def _win_write_cmd(name: str, action: str) -> Path:
    dest = _win_autostart_dir() / f"{name}.cmd"
    python = _win_python()
    main_py = _project_dir() / "main.py"
    log_file = _project_dir() / "pc_monitor_task.log"
    dest.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        f'cd /d "{_project_dir()}"\r\n'
        "set PYTHONUNBUFFERED=1\r\n"
        f'"{python}" -u "{main_py}" {action} >> "{log_file}" 2>&1\r\n',
        encoding="utf-8-sig",
    )
    return dest


def _schtasks(args: list[str], timeout: int = 8) -> subprocess.CompletedProcess:
    try:
        return _run(["schtasks", *args], timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(["schtasks", *args], 124, "", "timeout")


def _win_create_task(name: str, script: Path, extra: list[str]) -> subprocess.CompletedProcess:
    tr = f'"{script}"'
    create = [
        "schtasks", "/Create", "/F",
        "/TN", name,
        "/TR", tr,
        *extra,
    ]
    result = _run(create)
    if result.returncode != 0 and "/DELAY" in extra:
        stripped = [item for item in extra if item not in ("/DELAY", "0000:30")]
        create = ["schtasks", "/Create", "/F", "/TN", name, "/TR", tr, *stripped]
        result = _run(create)
    return result


def _win_err_text(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or "").strip()


def _win_is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _win_result_path() -> Path:
    return _win_autostart_dir() / "last_cli_result.txt"


def _win_save_cli_result(ok: bool, msg: str) -> None:
    if _os() != "Windows":
        return
    _win_result_path().write_text(("OK\n" if ok else "FAIL\n") + msg, encoding="utf-8")


def _win_load_cli_result() -> tuple[bool, str] | None:
    path = _win_result_path()
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    first, _, rest = text.partition("\n")
    return first.strip() == "OK", rest.strip() or text.strip()


def _win_run_as_admin(action_args: list[str]) -> tuple[int, str]:
    """Chay lai main.py bang UAC (Run as administrator) va cho xong."""
    python = _win_python()
    main_py = str(_project_dir() / "main.py")
    args = [main_py, *action_args]
    ps_args = ", ".join(json.dumps(a) for a in args)
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        "try {\n"
        f"  $p = Start-Process -FilePath {json.dumps(python)} "
        f"-ArgumentList @({ps_args}) "
        "-Verb RunAs -Wait -PassThru\n"
        "  if ($null -eq $p) { exit 1223 }\n"
        "  exit $p.ExitCode\n"
        "} catch {\n"
        "  $m = $_.Exception.Message\n"
        "  if ($m -match 'cancel') { exit 1223 }\n"
        "  [Console]::Error.WriteLine($m)\n"
        "  exit 1\n"
        "}\n"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=180,
    )
    err = (result.stderr or result.stdout or "").strip()
    return result.returncode, err


def _win_elevate_action(action: str, extra_args: list[str] | None = None) -> tuple[bool, str]:
    extra_args = extra_args or []
    try:
        _win_result_path().unlink(missing_ok=True)
    except OSError:
        pass
    try:
        code, err = _win_run_as_admin([action, "--elevated", *extra_args])
    except subprocess.TimeoutExpired:
        return (
            False,
            "Het thoi gian cho hop thoai Administrator (UAC).\n"
            "Hay chay lai: python main.py install\n"
            "Khi Windows hoi quyen, bam Yes.",
        )
    loaded = _win_load_cli_result()
    canceled = code == 1223 or "cancel" in (err or "").lower()
    if canceled:
        return False, "UAC_CANCELED"
    if loaded:
        return loaded
    if code == 0:
        return True, f"Da chay {action} voi quyen Administrator."
    return (
        False,
        err or f"Khong chay duoc voi quyen Administrator (exit {code}).",
    )


def _win_maybe_elevate(action: str, extra_args: list[str] | None = None) -> tuple[bool, str] | None:
    """None = dang la admin, cu tiep tuc. Nguoc lai = ket qua sau khi elevate."""
    if "--elevated" in sys.argv or _win_is_admin():
        return None
    return _win_elevate_action(action, extra_args)


def _win_access_denied(err: str) -> bool:
    low = err.lower()
    return "access is denied" in low or "access denied" in low or "truy cap bi tu choi" in low


def _win_denied_help() -> str:
    return (
        "Can quyen Administrator de tao Task Scheduler.\n"
        "Chay dung 1 lenh (Windows se hoi UAC, bam Yes):\n"
        "python main.py install"
    )


def _win_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _install_windows_startup_folder(cmds: dict[str, Path]) -> tuple[bool, str]:
    dest_dir = _win_startup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    listen_vbs = _win_write_listen_vbs()
    mapping = [
        ("PCMonitorPro_Startup.cmd", cmds["PCMonitorPro_Startup"]),
        ("PCMonitorPro_Listener.vbs", listen_vbs),
    ]
    lines = [
        "Da dang ky thu muc Startup (an, khong mo CMD):",
        f"Thu muc: {dest_dir}",
    ]
    for name, src in mapping:
        dest = dest_dir / name
        if name.endswith(".vbs"):
            dest.write_bytes(src.read_bytes())
        else:
            dest.write_text(
                "@echo off\r\n"
                f'call "{src}"\r\n',
                encoding="utf-8-sig",
            )
        lines.append(f"- {name}: OK")
    lines.append("Lan sau CHI CAN DANG NHAP Windows — khong can chay python main.py listen.")
    return True, "\n".join(lines)


def _uninstall_windows_startup_folder() -> list[str]:
    dest_dir = _win_startup_dir()
    notes = []
    for name in WIN_STARTUP_CMDS:
        path = dest_dir / name
        if path.exists():
            path.unlink()
            notes.append(f"- Startup {name}: da xoa")
        else:
            notes.append(f"- Startup {name}: khong co")
    return notes


def _install_windows(*, start_listener_now: bool) -> tuple[bool, str]:
    extra = [] if start_listener_now else ["--keep-listener"]
    elevated = _win_maybe_elevate("install", extra)
    if elevated is not None:
        ok, msg = elevated
        if msg == "UAC_CANCELED":
            cmds = {
                "PCMonitorPro_Startup": _win_write_cmd("startup", "startup"),
                "PCMonitorPro_Listener": _win_write_listen_vbs(),
            }
            fallback_ok, fallback = _install_windows_startup_folder(cmds)
            return fallback_ok, (
                "Ban da huy hop thoai Administrator (UAC).\n"
                "Chay lai 1 lenh roi bam Yes de dang ky Task Scheduler:\n"
                "python main.py install\n\n"
                + fallback
            )
        return ok, msg

    minutes = max(1, int(config.HEARTBEAT_MINUTES))
    python = _win_python()
    if "WindowsApps" in python:
        return (
            False,
            "Windows dang dung Python tu Microsoft Store (WindowsApps). "
            "Task Scheduler khong chay duoc stub nay nen bot se im lang.\n"
            "Hay cai Python tu https://python.org (tick Add python.exe to PATH), "
            "roi chay lai: python main.py install",
        )

    cmds = {
        "PCMonitorPro_Startup": _win_write_cmd("startup", "startup"),
        "PCMonitorPro_Listener": _win_write_listen_vbs(),
        "PCMonitorPro_Heartbeat": _win_write_cmd("heartbeat", "heartbeat"),
    }
    specs = [
        ("PCMonitorPro_Startup", ["/SC", "ONLOGON", "/DELAY", "0000:30"]),
        ("PCMonitorPro_Listener", ["/SC", "ONLOGON", "/DELAY", "0000:30"]),
        ("PCMonitorPro_Heartbeat", ["/SC", "MINUTE", "/MO", str(minutes)]),
    ]
    lines = ["Da dang ky Task Scheduler (chay khi dang nhap):"]
    for name, extra in specs:
        result = _win_create_task(name, cmds[name], extra)
        if result.returncode != 0:
            err = _win_err_text(result)
            if _win_access_denied(err):
                # Da chay voi Admin ma van bi chan (policy). Fallback Startup.
                ok, fallback = _install_windows_startup_folder(cmds)
                prefix = (
                    f"schtasks {name} that bai: {err}\n"
                    f"{_win_denied_help()}\n"
                )
                if ok:
                    extra = ""
                    if start_listener_now and not running_as_listener():
                        extra = (
                            "\n\nDe bot tra loi ngay (chua doi dang nhap lai):\n"
                            "python main.py listen"
                        )
                    return True, prefix + "\n" + fallback + extra
                return False, prefix + "\nKhong ghi duoc thu muc Startup: " + fallback
            return False, f"schtasks {name} that bai: {err or result.returncode}"
        extra_note = ""
        if name == "PCMonitorPro_Listener" and running_as_listener() and not start_listener_now:
            extra_note = " (giu listener hien tai)"
        lines.append(f"- {name}: OK{extra_note}")

    _, startup_msg = _install_windows_startup_folder(cmds)
    lines.append(startup_msg)

    if start_listener_now and not running_as_listener():
        started = _schtasks(["/Run", "/TN", "PCMonitorPro_Listener"])
        ping = _schtasks(["/Run", "/TN", "PCMonitorPro_Startup"])
        if started.returncode == 0:
            lines.append("- Da start listener ngay (khong can doi dang nhap lai)")
        else:
            err = (started.stderr or started.stdout or "").strip()
            lines.append(
                "- Chua start duoc listener ngay. Hay chay: python main.py listen\n"
                f"  Chi tiet: {err or started.returncode}"
            )
        if ping.returncode == 0:
            lines.append("- Da gui tin startup toi Telegram de kiem tra phan hoi")
        lines.append("Neu van im lang: xem pc_monitor.log va pc_monitor_task.log")

    lines.append("Kiem tra: schtasks /Query /TN PCMonitorPro_Listener")
    return True, "\n".join(lines)


def _uninstall_windows() -> tuple[bool, str]:
    elevated = _win_maybe_elevate("uninstall")
    if elevated is not None:
        ok, msg = elevated
        if msg == "UAC_CANCELED":
            notes = _uninstall_windows_startup_folder()
            return True, (
                "Ban da huy hop thoai Administrator (UAC), "
                "nen chi go duoc thu muc Startup.\n"
                "Chay lai: python main.py uninstall  roi bam Yes "
                "de xoa Task Scheduler.\n"
                + "\n".join(notes)
            )
        return ok, msg

    lines = ["Da go Task Scheduler:"]
    for name in WIN_TASKS:
        _schtasks(["/Delete", "/F", "/TN", name])
        lines.append(f"- {name}: da xoa (neu co)")
    lines.append("Thu muc Startup:")
    lines.extend(_uninstall_windows_startup_folder())
    return True, "\n".join(lines)


def _status_windows() -> str:
    lines = ["Windows Task Scheduler:"]
    for name in WIN_TASKS:
        result = _schtasks(["/Query", "/TN", name], timeout=5)
        if result.returncode == 124 or (result.stderr or "") == "timeout":
            lines.append(f"- {name}: khong doc duoc (Task Scheduler cham sau reboot)")
        elif result.returncode == 0:
            running = "Ready/Running"
            blob = (result.stdout or "").lower()
            if "running" in blob:
                running = "dang chay"
            elif "ready" in blob:
                running = "san sang"
            lines.append(f"- {name}: da dang ky ({running})")
        else:
            lines.append(f"- {name}: chua dang ky")
    dest_dir = _win_startup_dir()
    lines.append("Thu muc Startup:")
    for name in WIN_STARTUP_CMDS:
        path = dest_dir / name
        lines.append(f"- {name}: {'co' if path.exists() else 'chua co'}")
    return "\n".join(lines)


# --------------------------------- Public ------------------------------------

def install(*, start_listener_now: bool | None = None) -> tuple[bool, str]:
    """Dang ky service khoi dong. Tra ve (ok, thong_bao)."""
    if start_listener_now is None:
        start_listener_now = not running_as_listener()
    system = _os()
    try:
        if system == "Darwin":
            return _install_macos(start_listener_now=start_listener_now)
        if system == "Linux":
            return _install_linux(start_listener_now=start_listener_now)
        if system == "Windows":
            return _install_windows(start_listener_now=start_listener_now)
        return False, f"He dieu hanh {system} chua duoc ho tro."
    except FileNotFoundError as e:
        return False, f"Thieu cong cu he thong: {e}"
    except subprocess.TimeoutExpired:
        return False, "Het thoi gian khi dang ky service."
    except Exception as e:
        return False, f"Loi khi dang ky service: {e}"


def uninstall() -> tuple[bool, str]:
    system = _os()
    try:
        if system == "Darwin":
            return _uninstall_macos()
        if system == "Linux":
            return _uninstall_linux()
        if system == "Windows":
            return _uninstall_windows()
        return False, f"He dieu hanh {system} chua duoc ho tro."
    except Exception as e:
        return False, f"Loi khi go service: {e}"


def takeover_requested() -> bool:
    path = config.TAKEOVER_FILE
    if not path.exists():
        return False
    try:
        ts = float(path.read_text(encoding="utf-8").strip())
        return (time.time() - ts) < 45
    except Exception:
        return False


def _is_listen_cmdline(parts: list[str], project: str) -> bool:
    if "listen" not in parts:
        return False
    return any("main.py" in p.replace("\\", "/") for p in parts)


def _own_process_tree_pids() -> set[int]:
    """py.exe / Git Bash / pythonw cha-con — khong duoc taskkill."""
    pids = {os.getpid()}
    try:
        pids.add(os.getppid())
    except Exception:
        pass
    try:
        import psutil
        proc = psutil.Process()
        current = proc
        for _ in range(8):
            pids.add(current.pid)
            parent = current.parent()
            if parent is None:
                break
            current = parent
        for child in proc.children(recursive=True):
            pids.add(child.pid)
    except Exception:
        pass
    return pids


def _other_listener_pids() -> list[int]:
    try:
        import psutil
    except ImportError:
        return []
    skip = _own_process_tree_pids()
    project = str(_project_dir().resolve()).replace("\\", "/").rstrip("/").lower()
    pids = []
    deadline = time.time() + 2.0
    try:
        for proc in psutil.process_iter(["pid", "cmdline"]):
            if time.time() > deadline:
                break
            try:
                pid = proc.info.get("pid")
                if not pid or int(pid) in skip:
                    continue
                parts = [str(x) for x in (proc.info.get("cmdline") or [])]
                if _is_listen_cmdline(parts, project):
                    pids.append(int(pid))
            except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
                continue
    except (psutil.AccessDenied, PermissionError):
        return pids
    return pids


def _pause_managed_listener() -> list[str]:
    """Dung process do OS giu, giu lich dang ky cho lan dang nhap sau."""
    notes = []
    system = _os()
    try:
        if system == "Windows":
            result = _run(["schtasks", "/End", "/TN", "PCMonitorPro_Listener"], timeout=5)
            if result.returncode == 0:
                notes.append("Da dung task PCMonitorPro_Listener (lich van giu)")
            return notes
        if system == "Darwin":
            _, domain = _macos_uid_domain()
            result = _run(
                ["launchctl", "bootout", f"{domain}/com.pcmonitor.listener"],
                timeout=5,
            )
            if result.returncode == 0:
                notes.append("Da unload launchd listener trong phien nay")
            return notes
        if system == "Linux":
            result = _run(
                ["systemctl", "--user", "stop", "pcmonitor-listener.service"],
                timeout=5,
            )
            if result.returncode == 0:
                notes.append("Da stop systemd listener (van enable)")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        notes.append("Bo qua dung service cu (het thoi gian / thieu lenh)")
    return notes


def _force_kill(pid: int) -> None:
    if pid in _own_process_tree_pids():
        return
    if _os() == "Windows":
        _run(["taskkill", "/PID", str(pid), "/F"], timeout=5)
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def takeover_existing_listener() -> str:
    """Ghi de listen cu (service an / terminal cu). Khong can admin."""
    notes = _pause_managed_listener()
    pids = [p for p in _other_listener_pids() if p not in _own_process_tree_pids()]
    if pids:
        try:
            config.TAKEOVER_FILE.write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass
        try:
            import psutil
        except ImportError:
            psutil = None
        own = _own_process_tree_pids()
        for pid in pids:
            if pid in own:
                continue
            try:
                if psutil:
                    psutil.Process(pid).terminate()
                else:
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        time.sleep(0.4)
        for pid in list(pids):
            still = False
            if psutil:
                still = psutil.pid_exists(pid)
            else:
                try:
                    os.kill(pid, 0)
                    still = True
                except OSError:
                    still = False
            if still:
                _force_kill(pid)
        time.sleep(0.3)
        notes.append("Da tat listen cu: " + ", ".join(f"PID {p}" for p in pids))
    else:
        notes.append("Listen dang chay mot minh (binh thuong, khong can listen cu)")
    try:
        config.TAKEOVER_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        config.LISTENER_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    return "; ".join(notes)


def is_listener_running() -> tuple[bool, str]:
    """Process 'main.py listen' co dang chay khong (khac voi da dang ky autostart)."""
    if running_as_listener():
        return True, f"Dang chay trong process nay (PID {os.getpid()})"
    pids = _other_listener_pids()
    if pids:
        return True, "Process listen: " + ", ".join(f"PID {p}" for p in pids[:5])
    return False, "Khong thay process main.py listen"


def is_registered() -> tuple[bool, str]:
    try:
        return _is_autostart_registered()
    except Exception as e:
        return False, str(e)


def _is_autostart_registered(*, skip_schtasks: bool = False) -> tuple[bool, str]:
    """Listener co duoc dang ky chay luc dang nhap khong."""
    system = _os()
    if system == "Windows":
        startup = _win_startup_dir() / "PCMonitorPro_Listener.vbs"
        startup_cmd = _win_startup_dir() / "PCMonitorPro_Listener.cmd"
        if startup.exists() or startup_cmd.exists():
            return True, "Thu muc Startup (chay an luc dang nhap)"
        if skip_schtasks:
            return False, "Khong thay file Startup (bo qua Task Scheduler de khong treo)"
        task = _schtasks(["/Query", "/TN", "PCMonitorPro_Listener"], timeout=2)
        if task.returncode == 0:
            return True, "Task Scheduler: PCMonitorPro_Listener"
        if task.returncode == 124 or (task.stderr or "") == "timeout":
            return False, "Task Scheduler cham sau reboot, chua xac dinh duoc"
        return False, "Chua co task Listener va chua co file Startup"
    if system == "Darwin":
        dest = _macos_plist_path("listener")
        if dest.exists():
            return True, "launchd: com.pcmonitor.listener"
        return False, "Chua co LaunchAgent listener"
    if system == "Linux":
        result = _systemctl(["is-enabled", "pcmonitor-listener.service"])
        enabled = (result.stdout or "").strip()
        if enabled in ("enabled", "enabled-runtime", "static"):
            return True, f"systemd: pcmonitor-listener.service ({enabled})"
        return False, f"systemd listener: {enabled or 'chua dang ky'}"
    return False, f"He dieu hanh {system} chua ho tro"


def status_text(*, fast: bool = True) -> str:
    system = _os()
    try:
        ok, detail = _is_autostart_registered(skip_schtasks=fast)
    except Exception as e:
        ok, detail = False, str(e)
    try:
        live, live_detail = is_listener_running()
    except Exception as e:
        live, live_detail = False, str(e)

    if ok:
        verdict = f"✅ <b>DA DANG KY AUTOSTART</b>\n{_html(detail)}"
    else:
        verdict = (
            f"❌ <b>CHUA DANG KY AUTOSTART</b>\n{_html(detail)}\n"
            "Listen tay khac service. Gui /autostart (hoac tren may: "
            "<code>python main.py install</code>) de lan sau dang nhap tu chay."
        )
    if live:
        listen_line = f"✅ <b>LISTEN DANG CHAY</b>\n{_html(live_detail)}"
    else:
        listen_line = (
            f"❌ <b>LISTEN KHONG CHAY</b>\n{_html(live_detail)}\n"
            "Autostart moi la lich. Can dang nhap Windows/macOS, "
            "hoac chay: <code>python main.py listen</code>"
        )
    hint = ""
    if live and not ok:
        hint = (
            "\n➡️ <b>Dang chay bang tay</b> (python main.py listen), "
            "chua co service khoi dong. Gui /autostart de dang ky.\n"
        )
    elif not live and ok:
        hint = (
            "\n➡️ Service da dang ky nhung process chua chay. "
            "Dang nhap lai may, hoac chay <code>python main.py listen</code>.\n"
        )
    header = (
        f"SERVICE KHOI DONG\n"
        f"{verdict}\n"
        f"{listen_line}\n"
        f"{hint}"
        f"May: {_html(config.COMPUTER_NAME)}\n"
        f"He dieu hanh: {_html(system)}\n"
        f"Python: {_html(_python_bin())}\n"
    )
    try:
        if fast and system == "Windows":
            dest_dir = _win_startup_dir()
            body_lines = ["Windows (khong cho Task Scheduler):"]
            for name in WIN_STARTUP_CMDS:
                path = dest_dir / name
                body_lines.append(f"- {name}: {'co' if path.exists() else 'chua co'}")
            body = "\n".join(body_lines)
        elif system == "Darwin":
            body = _status_macos()
        elif system == "Linux":
            body = _status_linux()
        elif system == "Windows":
            body = _status_windows()
        else:
            body = "He dieu hanh chua duoc ho tro."
    except Exception as e:
        body = f"Khong doc duoc trang thai: {e}"
    text = header + "\n" + _html(body)
    if len(text) > 3500:
        text = text[:3490] + "\n…"
    return text


def run_cli(action: str) -> None:
    if action == "install":
        config.validate()
        keep_listener = "--keep-listener" in sys.argv
        ok, msg = install(start_listener_now=not keep_listener)
    elif action == "uninstall":
        ok, msg = uninstall()
    elif action in ("service", "autostart_status"):
        print(
            status_text(fast=False)
            .replace("<b>", "")
            .replace("</b>", "")
            .replace("<code>", "")
            .replace("</code>", "")
        )
        sys.exit(0)
    else:
        print(f"Lenh service khong hop le: {action}")
        sys.exit(1)
    _win_save_cli_result(ok, msg)
    print(msg)
    sys.exit(0 if ok else 1)
