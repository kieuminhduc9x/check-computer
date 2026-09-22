"""
vpn.py - Bat / tat profile Pritunl Client da import (CLI, khong can GUI).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path

from . import config


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


def list_profiles() -> tuple[bool, str, list[dict]]:
    try:
        result = _run_client(["list", "--json"])
        blob = (result.stdout or "").strip()
        if result.returncode == 0 and blob.startswith(("{", "[")):
            profiles = _parse_json_profiles(blob)
            if profiles:
                return True, "", profiles
        result = _run_client(["list"])
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            return False, err or f"pritunl-client list that bai ({result.returncode})", []
        profiles = _parse_text_profiles(result.stdout or "")
        return True, "", profiles
    except FileNotFoundError:
        return False, (
            "Chua cai Pritunl Client hoac khong tim thay CLI.\n"
            "Windows: C:\\Program Files (x86)\\Pritunl\\pritunl-client.exe"
        ), []
    except subprocess.TimeoutExpired:
        return False, "pritunl-client het thoi gian.", []
    except Exception as e:
        return False, str(e), []


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
    lines.append("Bật tat ca: /vpn_on   |  Tắt tat ca: /vpn_off")
    lines.append("Mot profile: /vpn_on ten_hoac_id")
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
