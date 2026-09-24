"""Tien ich: file, clipboard, am luong, pin, nhiet do, Wake-on-LAN, remote desktop."""

from __future__ import annotations

import os
import platform
import re
import socket
import subprocess
from pathlib import Path

from . import config

_MAC = re.compile(r"^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$", re.I)


def _os() -> str:
    return platform.system()


def _run(args: list[str], timeout: int = 15, input_text: str | None = None) -> subprocess.CompletedProcess:
    kwargs: dict = {
        "args": args,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "input": input_text,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.run(**kwargs)


def _home() -> Path:
    return Path.home().resolve()


def resolve_user_path(raw: str) -> Path:
    text = (raw or "").strip().strip('"')
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = _home() / path
    return path.resolve()


def _under_home_or_inbox(path: Path) -> bool:
    home = _home()
    inbox = config.INBOX_DIR.resolve()
    try:
        path.relative_to(home)
        return True
    except ValueError:
        pass
    try:
        path.relative_to(inbox)
        return True
    except ValueError:
        return False


def prepare_get(raw: str) -> tuple[bool, str]:
    if not raw.strip():
        return False, "Dung: /get duong-dan. Vi du /get Desktop/a.pdf hoac /get C:\\Users\\ban\\a.pdf"
    path = resolve_user_path(raw)
    if not _under_home_or_inbox(path):
        return False, "Chi lay file trong thu muc nguoi dung hoac inbox."
    if path.is_dir():
        names = []
        try:
            for child in sorted(path.iterdir())[:30]:
                kind = "/" if child.is_dir() else ""
                names.append(child.name + kind)
        except OSError as e:
            return False, str(e)
        listing = "\n".join(names) or "(trong)"
        return False, f"Day la thu muc:\n{listing}"
    if not path.is_file():
        return False, f"Khong thay file: {path}"
    size = path.stat().st_size
    limit = config.FILE_MAX_MB * 1024 * 1024
    if size > limit:
        return False, f"File {size // (1024 * 1024)}MB, gioi han Telegram {config.FILE_MAX_MB}MB."
    return True, str(path)


def save_upload(filename: str, data: bytes, caption: str = "") -> tuple[bool, str]:
    name = Path(filename or "file.bin").name
    if not name or name in (".", ".."):
        name = "file.bin"
    dest_hint = (caption or "").strip()
    if dest_hint.startswith("/put"):
        dest_hint = dest_hint[4:].strip()
    if dest_hint:
        dest = resolve_user_path(dest_hint)
        if dest.is_dir() or dest_hint.endswith(("/", "\\")):
            dest = dest / name
    else:
        config.INBOX_DIR.mkdir(parents=True, exist_ok=True)
        dest = config.INBOX_DIR / name
    dest = dest.resolve()
    if not _under_home_or_inbox(dest):
        return False, "Chi luu file trong thu muc nguoi dung hoac inbox."
    limit = min(config.FILE_MAX_MB, 20) * 1024 * 1024
    if len(data) > limit:
        return False, f"File qua {limit // (1024 * 1024)}MB, Telegram bot tai toi da 20MB."
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True, str(dest)


def clipboard_get() -> tuple[bool, str]:
    system = _os()
    try:
        if system == "Darwin":
            result = _run(["pbpaste"])
        elif system == "Windows":
            result = _run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"])
        else:
            result = _run(["wl-paste", "-n"])
            if result.returncode != 0:
                result = _run(["xclip", "-selection", "clipboard", "-o"])
        text = (result.stdout or "").strip()
        if result.returncode != 0 and not text:
            return False, (result.stderr or "Khong doc duoc clipboard").strip()[:300]
        if not text:
            return True, "(clipboard trong)"
        return True, text[:3500]
    except Exception as e:
        return False, str(e)


def clipboard_set(text: str) -> tuple[bool, str]:
    system = _os()
    try:
        if system == "Darwin":
            result = _run(["pbcopy"], input_text=text)
        elif system == "Windows":
            result = _run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                input_text=text,
            )
        else:
            result = _run(["wl-copy"], input_text=text)
            if result.returncode != 0:
                result = _run(["xclip", "-selection", "clipboard"], input_text=text)
        if result.returncode != 0:
            return False, (result.stderr or "Khong ghi clipboard")[:300]
        return True, f"Da chep {len(text)} ky tu vao clipboard."
    except Exception as e:
        return False, str(e)


def battery_text() -> str:
    from . import system_info
    text = system_info.get_battery_text()
    return text or "May khong co pin (may de ban)."


def temperature_text() -> str:
    try:
        import psutil
        data = psutil.sensors_temperatures() or {}
    except Exception as e:
        return f"Khong doc nhiet do: {e}"
    if not data:
        return "May khong bao nhiet do qua psutil (thuong gap tren Windows)."
    lines = []
    for name, entries in list(data.items())[:8]:
        for entry in entries[:3]:
            label = entry.label or name
            lines.append(f"{label}: {entry.current:.0f}C")
    return "\n".join(lines) or "Khong co so nhiet do."


def _volume_macos(level: int | None) -> tuple[bool, str]:
    if level is None:
        result = _run(["osascript", "-e", "output volume of (get volume settings)"])
        if result.returncode != 0:
            return False, (result.stderr or "Khong doc am luong")[:200]
        return True, f"Am luong: {(result.stdout or '').strip()}%"
    result = _run(["osascript", "-e", f"set volume output volume {level}"])
    if result.returncode != 0:
        return False, (result.stderr or "Khong dat am luong")[:200]
    return True, f"Da dat am luong {level}%."


def _volume_linux(level: int | None) -> tuple[bool, str]:
    if level is None:
        result = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        blob = (result.stdout or result.stderr or "").strip()
        match = re.search(r"(\d+)%", blob)
        if match:
            return True, f"Am luong: {match.group(1)}%"
        return False, blob[:200] or "Can pactl (PulseAudio/PipeWire)."
    result = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
    if result.returncode != 0:
        return False, (result.stderr or "Khong dat am luong")[:200]
    return True, f"Da dat am luong {level}%."


def _volume_windows(level: int | None) -> tuple[bool, str]:
    script = r'''
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
namespace PcMonAudio {
  [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioEndpointVolume {
    int RegisterControlChangeNotify(IntPtr p);
    int UnregisterControlChangeNotify(IntPtr p);
    int GetChannelCount(out uint n);
    int SetMasterVolumeLevel(float db, ref Guid ctx);
    int SetMasterVolumeLevelScalar(float level, ref Guid ctx);
    int GetMasterVolumeLevel(out float db);
    int GetMasterVolumeLevelScalar(out float level);
    int SetChannelVolumeLevel(uint ch, float db, ref Guid ctx);
    int SetChannelVolumeLevelScalar(uint ch, float level, ref Guid ctx);
    int GetChannelVolumeLevel(uint ch, out float db);
    int GetChannelVolumeLevelScalar(uint ch, out float level);
    int SetMute([MarshalAs(UnmanagedType.Bool)] bool mute, ref Guid ctx);
    int GetMute(out bool mute);
  }
  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice {
    int Activate(ref Guid iid, int cls, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
  }
  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator {
    int EnumAudioEndpoints(int flow, int state, out IntPtr devices);
    int GetDefaultAudioEndpoint(int flow, int role, out IMMDevice device);
  }
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
  class MMDeviceEnumerator {}
  public class Vol {
    static IAudioEndpointVolume Endpoint() {
      var en = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
      IMMDevice dev;
      en.GetDefaultAudioEndpoint(0, 1, out dev);
      var iid = typeof(IAudioEndpointVolume).GUID;
      object obj;
      dev.Activate(ref iid, 23, IntPtr.Zero, out obj);
      return (IAudioEndpointVolume)obj;
    }
    public static int GetPercent() {
      float level;
      Endpoint().GetMasterVolumeLevelScalar(out level);
      return (int)Math.Round(level * 100);
    }
    public static void SetPercent(int percent) {
      var ctx = Guid.Empty;
      Endpoint().SetMasterVolumeLevelScalar(percent / 100f, ref ctx);
    }
  }
}
"@
if ("__LEVEL__" -ne "") { [PcMonAudio.Vol]::SetPercent([int]"__LEVEL__"); [PcMonAudio.Vol]::GetPercent() }
else { [PcMonAudio.Vol]::GetPercent() }
'''
    script = script.replace("__LEVEL__", "" if level is None else str(int(level)))
    result = _run(["powershell", "-NoProfile", "-Command", script], timeout=25)
    blob = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    match = re.search(r"(\d+)\s*$", blob)
    if result.returncode == 0 and match:
        if level is None:
            return True, f"Am luong: {match.group(1)}%"
        return True, f"Da dat am luong {match.group(1)}%."
    return False, (blob or "Khong doi am luong")[:300]


def volume(level: int | None) -> tuple[bool, str]:
    if level is not None:
        level = max(0, min(100, level))
    system = _os()
    if system == "Darwin":
        return _volume_macos(level)
    if system == "Linux":
        return _volume_linux(level)
    if system == "Windows":
        return _volume_windows(level)
    return False, f"Chua ho tro am luong tren {system}"


def parse_wol_targets() -> list[tuple[str, str]]:
    items = []
    for part in config.WOL_TARGETS.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, mac = part.split("=", 1)
        else:
            name, mac = part, part
        items.append((name.strip(), mac.strip()))
    return items


def send_wol(mac: str, broadcast: str | None = None) -> tuple[bool, str]:
    cleaned = mac.strip().replace("-", ":")
    if not _MAC.match(cleaned):
        return False, "MAC khong hop le. Vi du AA:BB:CC:DD:EE:FF"
    raw = bytes.fromhex(cleaned.replace(":", ""))
    packet = b"\xff" * 6 + raw * 16
    host = broadcast or config.WOL_BROADCAST
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (host, 9))
        sock.sendto(packet, (host, 7))
    finally:
        sock.close()
    return True, f"Da gui Wake-on-LAN toi {cleaned} qua {host}. May dich phai bat WOL trong BIOS va card mang."


def wol_help() -> str:
    targets = parse_wol_targets()
    lines = [
        "Danh thuc may KHAC trong cung mang (may nay phai dang bat).",
        "May dang tat khong tu gui duoc goi danh thuc cho chinh no.",
        "Dung: /wol AA:BB:CC:DD:EE:FF",
    ]
    if targets:
        lines.append("Da cau hinh:")
        lines.extend(f"/wol {name}  ({mac})" for name, mac in targets)
    else:
        lines.append("Them trong .env: WOL_TARGETS=ten=AA:BB:CC:DD:EE:FF")
    return "\n".join(lines)


def resolve_wol(query: str) -> tuple[bool, str]:
    query = query.strip()
    if not query:
        return False, wol_help()
    for name, mac in parse_wol_targets():
        if query.lower() == name.lower():
            return send_wol(mac)
    return send_wol(query)


def _remote_candidates() -> list[list[str]]:
    if config.REMOTE_COMMAND:
        return [config.REMOTE_COMMAND.split()]
    system = _os()
    if system == "Windows":
        found = []
        for path in (
            r"C:\Program Files\RustDesk\rustdesk.exe",
            r"C:\Program Files (x86)\RustDesk\rustdesk.exe",
            r"C:\Program Files\AnyDesk\AnyDesk.exe",
            r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe",
        ):
            if Path(path).exists():
                found.append([path])
        found.append(["mstsc.exe"])
        return found
    if system == "Darwin":
        return [["open", "-a", "RustDesk"], ["open", "-a", "AnyDesk"], ["open", "/System/Library/CoreServices/Applications/Screen Sharing.app"]]
    return [["rustdesk"], ["anydesk"], ["remmina"]]


def launch_remote() -> tuple[bool, str]:
    errors = []
    for cmd in _remote_candidates():
        try:
            kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | 0x08000000
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen(cmd, **kwargs)
            return True, "Da mo " + " ".join(cmd)
        except Exception as e:
            errors.append(f"{cmd[0]}: {e}")
    return False, "Khong mo duoc RustDesk/AnyDesk/Remote Desktop.\n" + "\n".join(errors[:4])


def open_target(raw: str) -> tuple[bool, str] | None:
    """None neu khong phai URL/file. (ok, msg) neu mo duoc hoac loi ro."""
    text = (raw or "").strip().strip('"')
    if not text:
        return None
    lower = text.lower()
    is_url = lower.startswith("http://") or lower.startswith("https://")
    path = None
    if not is_url:
        candidate = resolve_user_path(text)
        if candidate.exists():
            path = candidate
        elif Path(text).exists():
            path = Path(text)
        else:
            return None
    system = _os()
    try:
        if system == "Windows":
            os.startfile(text if is_url else str(path))  # type: ignore[attr-defined]
        elif system == "Darwin":
            _run(["open", text if is_url else str(path)])
        else:
            _run(["xdg-open", text if is_url else str(path)])
        shown = text if is_url else str(path)
        return True, f"Da mo {shown}"
    except Exception as e:
        return False, str(e)
