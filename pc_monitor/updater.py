"""
updater.py - git pull --ff-only roi khoi dong lai listen (khong can gõ tay).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from . import config
from . import telegram_api


def _git(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(config.PROJECT_ROOT), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _out(result: subprocess.CompletedProcess) -> str:
    return ((result.stdout or "") + "\n" + (result.stderr or "")).strip()


def current_revision() -> str:
    result = _git("rev-parse", "--short", "HEAD")
    return (result.stdout or "").strip() or "?"


def pull_ff_only() -> tuple[bool, str, bool]:
    """Tra ve (ok, thong_bao, co_code_moi). Khong merge neu local sua file."""
    try:
        dirty = _git("status", "--porcelain")
        if dirty.returncode != 0:
            return False, "Thu muc khong phai git repo (hoac thieu git).", False
        tracked_dirty = []
        for line in (dirty.stdout or "").splitlines():
            if not line.strip():
                continue
            code = line[:2]
            if code.strip() == "?" or code == "!!":
                continue
            tracked_dirty.append(line)
        if tracked_dirty:
            preview = ", ".join(ln[3:].strip() for ln in tracked_dirty[:6])
            return False, f"Co thay doi local, khong tu pull: {preview}", False

        fetched = _git("fetch", "origin")
        if fetched.returncode != 0:
            return False, f"git fetch that bai: {_out(fetched)[:400]}", False

        before = current_revision()
        pulled = _git("pull", "--ff-only", "origin")
        if pulled.returncode != 0:
            return False, f"git pull --ff-only that bai: {_out(pulled)[:400]}", False
        after = current_revision()
        blob = _out(pulled).lower()
        if before == after or "already up to date" in blob or "already up-to-date" in blob:
            return True, f"Dang la ban moi nhat ({after}).", False
        return True, f"Da cap nhat {before} -> {after}.\n{_out(pulled)[:500]}", True
    except FileNotFoundError:
        return False, "May chua cai git.", False
    except subprocess.TimeoutExpired:
        return False, "git het thoi gian (mang/VPN?).", False
    except Exception as e:
        return False, str(e), False


def spawn_new_listener(*, notify_update: bool = True) -> None:
    """Mo listen an (pythonw) roi thoat process hien tai."""
    try:
        config.TAKEOVER_FILE.write_text(str(time.time()), encoding="utf-8")
        if notify_update:
            config.UPDATE_STAMP_FILE.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass

    python = sys.executable
    if os.name == "nt":
        pythonw = Path(python).with_name("pythonw.exe")
        if pythonw.exists():
            python = str(pythonw)

    env = os.environ.copy()
    env["PCMONITOR_ROLE"] = "listener"
    kwargs: dict = {
        "cwd": str(config.PROJECT_ROOT),
        "env": env,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | 0x08000000  # CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True

    main_py = str(config.PROJECT_ROOT / "main.py")
    subprocess.Popen([python, "-u", main_py, "listen"], **kwargs)
    telegram_api.log("Da spawn listen an, thoat process cua so.")
    os._exit(0)


def apply_and_restart() -> tuple[bool, str, bool]:
    """Pull; neu co commit moi thi restart listen. Tra ve (ok, msg, will_restart)."""
    ok, msg, changed = pull_ff_only()
    if ok and changed:
        return True, msg + "\nDang khoi dong lai listen...", True
    return ok, msg, False
