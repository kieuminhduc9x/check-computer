"""
vpn.py - Bat / tat profile Pritunl Client da import (CLI, khong can GUI).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path


def _os() -> str:
    return platform.system()


def _client_bin() -> str | None:
    env = os.getenv("PRITUNL_CLIENT", "").strip()
    if env and Path(env).exists():
        return env
    system = _os()
    candidates: list[str] = []
    if system == "Windows":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates = [
            str(Path(pf86) / "Pritunl" / "pritunl-client.exe"),
            str(Path(pf) / "Pritunl" / "pritunl-client.exe"),
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Pritunl.app/Contents/Resources/pritunl-client",
        ]
    candidates.append("pritunl-client")
    for path in candidates:
        p = Path(path)
        if p.exists():
            return str(p)
        if path == "pritunl-client":
            return path
    return None


def _run_client(args: list[str], timeout: int = 45) -> subprocess.CompletedProcess:
    bin_path = _client_bin()
    if not bin_path:
        raise FileNotFoundError("Khong tim thay pritunl-client")
    return subprocess.run(
        [bin_path, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _mode() -> str:
    val = (os.getenv("PRITUNL_MODE") or "ovpn").strip().lower()
    return val if val in ("ovpn", "wg") else "ovpn"


def _is_connected(profile: dict) -> bool:
    for key in ("status", "state", "run_state", "connection_status"):
        raw = profile.get(key)
        if raw is None:
            continue
        text = str(raw).strip().lower()
        if text in ("connected", "connecting", "active", "running", "true", "online"):
            return True
        if text in ("disconnected", "stopped", "inactive", "false", "offline"):
            return False
        if text == "1":
            return True
        if text == "0":
            return False
    return bool(profile.get("connected"))


def _parse_json_profiles(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("profiles") or data.get("data") or []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or item.get("profile_id") or "").strip()
        if not pid:
            continue
        name = str(item.get("name") or item.get("server") or pid)
        out.append({"id": pid, "name": name, "connected": _is_connected(item), "raw": item})
    return out


def _parse_text_profiles(text: str) -> list[dict]:
    profiles = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.lower().startswith("id") or set(line) <= set("- "):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pid = parts[0]
        status = parts[-1].lower() if len(parts) > 2 else ""
        name = " ".join(parts[1:-1]) if len(parts) > 2 else parts[1]
        connected = status in ("connected", "connecting", "active", "running", "online")
        profiles.append({"id": pid, "name": name, "connected": connected, "raw": {}})
    return profiles


def _profile_dirs() -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []
    appdata = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")
    programdata = os.environ.get("ProgramData", r"C:\ProgramData")
    if appdata:
        dirs.append(Path(appdata) / "pritunl" / "profiles")
    if local:
        dirs.append(Path(local) / "pritunl" / "profiles")
    dirs.extend(
        [
            Path(programdata) / "Pritunl" / "Profiles",
            Path(programdata) / "pritunl" / "profiles",
            Path(programdata) / "Pritunl" / "profiles",
            home / "Library" / "Application Support" / "pritunl" / "profiles",
            home / ".config" / "pritunl" / "profiles",
            Path("/var/lib/pritunl-client/profiles"),
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for item in dirs:
        key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _extract_json_obj(text: str) -> dict:
    blob = (text or "").strip()
    if not blob:
        return {}
    try:
        data = json.loads(blob)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    start = blob.find("{")
    end = blob.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(blob[start : end + 1])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _meta_from_ovpn(text: str) -> dict:
    chunks: list[str] = []
    collecting = False
    buf: list[str] = []
    uv_name = ""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("setenv UV_NAME "):
            uv_name = stripped[len("setenv UV_NAME ") :].strip().strip('"')
        if stripped == "#{":
            collecting = True
            buf = ["{"]
            continue
        if collecting:
            if stripped == "#}":
                buf.append("}")
                chunks.append("\n".join(buf))
                collecting = False
                buf = []
                continue
            if stripped.startswith("#"):
                buf.append(stripped[1:])
    for chunk in chunks:
        data = _extract_json_obj(chunk)
        if data:
            if uv_name and not data.get("name"):
                data["name"] = uv_name
            return data
    return {"name": uv_name} if uv_name else {}


def _display_name(data: dict, fallback: str) -> str:
    for key in ("name", "server", "organization", "user"):
        val = str(data.get(key) or "").strip()
        if val:
            return val
    return fallback


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except Exception:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return ""


def _profiles_from_disk() -> list[dict]:
    found: dict[str, dict] = {}
    for folder in _profile_dirs():
        if not folder.is_dir():
            continue
        try:
            files = list(folder.iterdir())
        except OSError:
            continue
        for path in sorted(files):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in (".conf", ".json", ".ovpn", ".pritunl"):
                continue
            raw = _read_text(path)
            if suffix == ".ovpn":
                data = _meta_from_ovpn(raw)
            else:
                data = _extract_json_obj(raw)
                ovpn_blob = str(data.get("ovpn_data") or "")
                if ovpn_blob and not data.get("name"):
                    extra = _meta_from_ovpn(ovpn_blob)
                    for key, val in extra.items():
                        data.setdefault(key, val)
            pid = str(data.get("id") or data.get("profile_id") or path.stem).strip()
            if not pid:
                continue
            name = _display_name(data, path.stem)
            key = pid.lower()
            current = found.get(key)
            if current is None or (name and name != path.stem and current["name"] == current["id"]):
                found[key] = {
                    "id": pid,
                    "name": name or pid,
                    "connected": _is_connected(data),
                    "raw": data,
                }
    return list(found.values())


def _cli_list_broken(text: str) -> bool:
    low = (text or "").lower()
    return "unmarshal" in low or "sprofile" in low


def _short_cli_error(text: str) -> str:
    if _cli_list_broken(text):
        return (
            "CLI Pritunl list bi loi tren Windows.\n"
            "Khong doc duoc ten profile tu o dia.\n"
            "Mo app Pritunl Client, import profile, roi gui /vpn lai."
        )
    line = (text or "").strip().splitlines()[0] if text else ""
    return line[:300] or "pritunl-client list that bai"


def _merge_profiles(disk: list[dict], cli_profiles: list[dict]) -> list[dict]:
    if not disk:
        return cli_profiles
    if not cli_profiles:
        return disk
    by_id = {p["id"].lower(): p for p in cli_profiles}
    out = []
    seen: set[str] = set()
    for item in disk:
        key = item["id"].lower()
        seen.add(key)
        other = by_id.get(key)
        if other:
            item = dict(item)
            item["connected"] = other["connected"]
            if other["name"] and other["name"] != other["id"]:
                item["name"] = other["name"]
        out.append(item)
    for item in cli_profiles:
        if item["id"].lower() not in seen:
            out.append(item)
    return out


def list_profiles() -> tuple[bool, str, list[dict]]:
    disk = _profiles_from_disk()
    cli_profiles: list[dict] = []
    err = ""
    try:
        result = _run_client(["list", "--json"], timeout=12)
        blob = (result.stdout or "").strip()
        if result.returncode == 0 and blob.startswith(("{", "[")):
            cli_profiles = _parse_json_profiles(blob)
        stderr = (result.stderr or result.stdout or "")
        if not cli_profiles and not _cli_list_broken(stderr):
            result = _run_client(["list"], timeout=12)
            if result.returncode == 0:
                cli_profiles = _parse_text_profiles(result.stdout or "")
            stderr = (result.stderr or result.stdout or "")
        if not cli_profiles:
            err = _short_cli_error(stderr)
    except FileNotFoundError:
        if disk:
            return True, "", disk
        return False, (
            "Chua cai Pritunl Client hoac khong tim thay CLI.\n"
            "Windows: C:\\Program Files (x86)\\Pritunl\\pritunl-client.exe"
        ), []
    except subprocess.TimeoutExpired:
        err = "pritunl-client het thoi gian."
    except Exception as e:
        err = str(e)[:200]
    profiles = _merge_profiles(disk, cli_profiles)
    if profiles:
        return True, "", profiles
    return False, err or (
        "Khong tim thay profile Pritunl.\n"
        "Mo app Pritunl Client, import VPN, roi gui /vpn lai."
    ), []


def match_profile(query: str, profiles: list[dict]) -> dict | None:
    q = query.strip().lower()
    if not q:
        return None
    for p in profiles:
        if p["id"].lower() == q or p["name"].lower() == q:
            return p
    hits = [p for p in profiles if p["id"].lower().startswith(q) or q in p["name"].lower()]
    if len(hits) == 1:
        return hits[0]
    return None


def start_profile(profile_id: str) -> tuple[bool, str]:
    args = ["start", profile_id, "--mode", _mode()]
    password = (os.getenv("PRITUNL_PASSWORD") or "").strip()
    if password:
        args.extend(["--password", password])
    try:
        result = _run_client(args, timeout=60)
    except FileNotFoundError as e:
        return False, str(e)
    except subprocess.TimeoutExpired:
        return False, f"Het thoi gian khi bat profile {profile_id}"
    if result.returncode == 0:
        return True, f"Da bat profile {profile_id} ({_mode()})"
    err = (result.stderr or result.stdout or "").strip()
    hint = ""
    low = err.lower()
    if "password" in low or "auth" in low or "otp" in low or "pin" in low:
        hint = " Profile can mat khau/OTP — dien PRITUNL_PASSWORD trong .env (khong commit)."
    return False, (err or f"start that bai ({result.returncode})") + hint


def stop_profile(profile_id: str) -> tuple[bool, str]:
    try:
        result = _run_client(["stop", profile_id], timeout=45)
    except FileNotFoundError as e:
        return False, str(e)
    except subprocess.TimeoutExpired:
        return False, f"Het thoi gian khi tat profile {profile_id}"
    if result.returncode == 0:
        return True, f"Da tat profile {profile_id}"
    err = (result.stderr or result.stdout or "").strip()
    return False, err or f"stop that bai ({result.returncode})"


def start_all() -> tuple[bool, str]:
    ok, err, profiles = list_profiles()
    if not ok:
        return False, err
    if not profiles:
        return True, "Khong co profile Pritunl nao (hay import trong client truoc)."
    lines = []
    any_ok = False
    for p in profiles:
        if p["connected"]:
            lines.append(f"- {p['name']}: da ket noi, bo qua")
            continue
        started, msg = start_profile(p["id"])
        any_ok = any_ok or started
        lines.append(f"- {p['name']}: {msg}")
    return any_ok or all(p["connected"] for p in profiles), "\n".join(lines)


def stop_all() -> tuple[bool, str]:
    ok, err, profiles = list_profiles()
    if not ok:
        return False, err
    if not profiles:
        return True, "Khong co profile Pritunl nao."
    lines = []
    for p in profiles:
        if not p["connected"]:
            lines.append(f"- {p['name']}: dang tat, bo qua")
            continue
        stopped, msg = stop_profile(p["id"])
        lines.append(f"- {p['name']}: {msg}")
    return True, "\n".join(lines)


def _html(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_list_text(profiles: list[dict]) -> str:
    if not profiles:
        return "Khong co profile Pritunl nao da import."
    lines = [f"🔐 <b>PRITUNL</b> ({len(profiles)} profile)"]
    for p in profiles:
        state = "🟢 connected" if p["connected"] else "⚪ disconnected"
        short = p["id"][:8]
        lines.append(f"- {_html(p['name'])}  <code>{_html(short)}</code>  {state}")
    lines.append("Bam nut Bat ... hoac gui /vpn_on ten")
    lines.append("Tat ca: /vpn_on    |    /vpn_off")
    return "\n".join(lines)


def list_keyboard(profiles: list[dict]) -> dict | None:
    if not profiles:
        return None
    rows = []
    for p in profiles[:8]:
        short = p["id"][:12]
        label = (p["name"] or short)[:28]
        if p["connected"]:
            rows.append([{"text": f"Tat {label}", "callback_data": f"vpn_off:{short}"}])
        else:
            rows.append([{"text": f"Bat {label}", "callback_data": f"vpn_on:{short}"}])
    rows.append([
        {"text": "Bat tat ca", "callback_data": "vpn_on_all"},
        {"text": "Tat tat ca", "callback_data": "vpn_off_all"},
    ])
    return {"inline_keyboard": rows}
