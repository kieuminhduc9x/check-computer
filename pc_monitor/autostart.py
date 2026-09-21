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
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=kwargs.pop("timeout", 30),
        **kwargs,
    )


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


def _install_macos(*, start_listener_now: bool) -> tuple[bool, str]:
    mapping = _mapping()
    templates = _project_dir() / "scripts" / "macos"
    lines = ["Da dang ky launchd (chay khi dang nhap):"]
    for name in MAC_LABELS:
        template = templates / f"com.pcmonitor.{name}.plist.template"
        dest = _macos_plist_path(name)
        if not template.exists():
            return False, f"Thieu template: {template}"
        _fill_template(template, dest, mapping)

        skip_reload = running_as_listener() and not start_listener_now and name in ("listener", "startup")
        if skip_reload:
            lines.append(f"- com.pcmonitor.{name}: da ghi file, giu process hien tai")
            continue

        _macos_launchctl(["unload", str(dest)])
        loaded = _macos_launchctl(["load", "-w", str(dest)])
        if loaded.returncode != 0:
            err = (loaded.stderr or loaded.stdout or "").strip()
            return False, f"launchctl load {name} that bai: {err or loaded.returncode}"
        lines.append(f"- com.pcmonitor.{name}: OK")
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


def _status_macos() -> str:
    listed = _macos_launchctl(["list"])
    blob = listed.stdout or ""
    lines = ["macOS launchd:"]
    for name in MAC_LABELS:
        label = f"com.pcmonitor.{name}"
        dest = _macos_plist_path(name)
        registered = dest.exists()
        loaded = label in blob
        state = []
        if loaded:
            state.append("dang nap")
        if registered:
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


def _schtasks(args: list[str]) -> subprocess.CompletedProcess:
    return _run(["schtasks", *args])


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
        f"-WorkingDirectory {json.dumps(str(_project_dir()))} "
        "-Verb RunAs -Wait -PassThru -WindowStyle Hidden\n"
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
    mapping = [
        ("PCMonitorPro_Startup.cmd", cmds["PCMonitorPro_Startup"]),
        ("PCMonitorPro_Listener.cmd", cmds["PCMonitorPro_Listener"]),
    ]
    lines = [
        "Da dang ky bang thu muc Startup (khong can Admin):",
        f"Thu muc: {dest_dir}",
    ]
    for name, src in mapping:
        dest = dest_dir / name
        dest.write_text(
            "@echo off\r\n"
            f'call "{src}"\r\n',
            encoding="utf-8-sig",
        )
        lines.append(f"- {name}: OK")
    lines.append("Lan sau dang nhap Windows se tu chay bot.")
    lines.append("Heartbeat dinh ky can Task Scheduler (quyen Admin) nen chua bat.")
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
                "PCMonitorPro_Listener": _win_write_cmd("listen", "listen"),
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
        "PCMonitorPro_Listener": _win_write_cmd("listen", "listen"),
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
        result = _schtasks(["/Query", "/TN", name])
        if result.returncode == 0:
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


def status_text() -> str:
    system = _os()
    header = (
        f"⚙️ <b>SERVICE KHOI DONG</b>\n"
        f"May: {config.COMPUTER_NAME}\n"
        f"He dieu hanh: {system}\n"
        f"Python: {_python_bin()}\n"
    )
    try:
        if system == "Darwin":
            body = _status_macos()
        elif system == "Linux":
            body = _status_linux()
        elif system == "Windows":
            body = _status_windows()
        else:
            body = "He dieu hanh chua duoc ho tro."
    except Exception as e:
        body = f"Khong doc duoc trang thai: {e}"
    return header + "\n" + body


def run_cli(action: str) -> None:
    if action == "install":
        config.validate()
        keep_listener = "--keep-listener" in sys.argv
        ok, msg = install(start_listener_now=not keep_listener)
    elif action == "uninstall":
        ok, msg = uninstall()
    elif action in ("service", "autostart_status"):
        print(status_text().replace("<b>", "").replace("</b>", ""))
        sys.exit(0)
    else:
        print(f"Lenh service khong hop le: {action}")
        sys.exit(1)
    _win_save_cli_result(ok, msg)
    print(msg)
    sys.exit(0 if ok else 1)
