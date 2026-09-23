"""
updater.py - git pull --ff-only roi khoi dong lai listen (khong can go tay).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config
from . import telegram_api

_git_lock = threading.Lock()


def _git_bin() -> str:
    env = os.getenv("GIT_EXECUTABLE", "").strip()
    if env and Path(env).exists():
        return env
    if os.name == "nt":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        for candidate in (
            Path(pf) / "Git" / "cmd" / "git.exe",
            Path(pf86) / "Git" / "cmd" / "git.exe",
            Path(local) / "Programs" / "Git" / "cmd" / "git.exe",
        ):
            if candidate.exists():
                return str(candidate)
    return "git"


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "echo"
    env["SSH_ASKPASS"] = "echo"
    env["GC_CONNECT_TIMEOUT"] = "15"
    env["GIT_HTTP_LOW_SPEED_LIMIT"] = "1000"
    env["GIT_HTTP_LOW_SPEED_TIME"] = "20"
    return env


def _git(*args: str, timeout: int = 25) -> subprocess.CompletedProcess:
    kwargs: dict = {
        "args": [_git_bin(), "-C", str(config.PROJECT_ROOT), *args],
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "env": _git_env(),
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.run(**kwargs)


def _out(result: subprocess.CompletedProcess) -> str:
    return ((result.stdout or "") + "\n" + (result.stderr or "")).strip()


def current_revision() -> str:
    result = _git("rev-parse", "--short", "HEAD", timeout=10)
    return (result.stdout or "").strip() or "?"


_SKIP_DIRTY_PREFIXES = (
    ".idea/",
    ".vscode/",
    "__pycache__/",
    ".autostart/",
)


def _is_skip_dirty(path: str) -> bool:
    p = path.replace("\\", "/").lstrip("./")
    if p.startswith(".idea") or p.startswith(".vscode"):
        return True
    return any(p.startswith(pref) or f"/{pref}" in f"/{p}" for pref in _SKIP_DIRTY_PREFIXES)


def _clear_stale_lock() -> None:
    lock = config.PROJECT_ROOT / ".git" / "index.lock"
    try:
        if not lock.exists():
            return
        age = time.time() - lock.stat().st_mtime
        if age > 90:
            lock.unlink()
            telegram_api.log("Da xoa .git/index.lock cu.")
    except OSError:
        pass


def pull_ff_only() -> tuple[bool, str, bool]:
    """Tra ve (ok, thong_bao, co_code_moi). Khong merge neu local sua file."""
    if config.is_frozen():
        return False, (
            "Ban dang chay file .exe — /update (git pull) khong dung duoc. "
            "Hay build exe moi roi copy de file cu, hoac dung ban Python + git."
        ), False
    if not _git_lock.acquire(timeout=3):
        return False, "Dang co git khac chay. Gui lai /update sau 20 giay.", False
    try:
        _clear_stale_lock()
        dirty = _git("status", "--porcelain", timeout=15)
        if dirty.returncode != 0:
            err = _out(dirty)[:300]
            return False, err or "Thu muc khong phai git repo (hoac thieu git).", False
        tracked_dirty = []
        for line in (dirty.stdout or "").splitlines():
            if not line.strip():
                continue
            code = line[:2]
            path = line[3:].strip().strip('"')
            if code == "??" or code == "!!" or "?" in code:
                continue
            if _is_skip_dirty(path):
                continue
            tracked_dirty.append(line)
        if tracked_dirty:
            preview = ", ".join(ln[3:].strip() for ln in tracked_dirty[:6])
            return False, f"Co thay doi local, khong tu pull: {preview}", False

        fetched = _git("fetch", "--prune", "origin", timeout=25)
        if fetched.returncode != 0:
            return False, f"git fetch that bai: {_out(fetched)[:400]}", False

        before = current_revision()
        branch = (_git("rev-parse", "--abbrev-ref", "HEAD", timeout=10).stdout or "").strip()
        pull_args = ["pull", "--ff-only", "origin"]
        if branch and branch != "HEAD":
            pull_args.append(branch)
        pulled = _git(*pull_args, timeout=40)
        if pulled.returncode != 0:
            return False, f"git pull --ff-only that bai: {_out(pulled)[:400]}", False
        after = current_revision()
        blob = _out(pulled).lower()
        if before == after or "already up to date" in blob or "already up-to-date" in blob:
            return True, f"Dang la ban moi nhat ({after}).", False
        return True, f"Da cap nhat {before} -> {after}.\n{_out(pulled)[:500]}", True
    except FileNotFoundError:
        return False, (
            "Khong tim thay git.exe (listen an thuong thieu PATH).\n"
            "Cai Git for Windows, hoac tren may chay: git pull roi python main.py listen."
        ), False
    except subprocess.TimeoutExpired:
        return False, "git het thoi gian (mang/VPN/GitHub?). Thu lai khi da co mang.", False
    except Exception as e:
        return False, str(e), False
    finally:
        _git_lock.release()


def spawn_new_listener(*, notify_update: bool = True, kind: str | None = None) -> None:
    """Mo listen an (pythonw) roi thoat process hien tai."""
    if kind is None:
        kind = "update" if notify_update else ""
    try:
        config.TAKEOVER_FILE.write_text(str(time.time()), encoding="utf-8")
        if kind:
            config.UPDATE_STAMP_FILE.write_text(f"{kind} {time.time()}", encoding="utf-8")
    except OSError:
        pass

    python = sys.executable
    if os.name == "nt" and not config.is_frozen():
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

    if config.is_frozen():
        cmd = [str(Path(sys.executable).resolve()), "listen"]
    else:
        cmd = [python, "-u", str(config.PROJECT_ROOT / "main.py"), "listen"]
    subprocess.Popen(cmd, **kwargs)
    try:
        from . import listener
        listener.wait_other_jobs(8)
    except Exception:
        time.sleep(1)
    telegram_api.log("Da spawn listen an, thoat process cua so.")
    os._exit(0)


def apply_and_restart() -> tuple[bool, str, bool]:
    """Pull; neu co commit moi thi restart listen. Tra ve (ok, msg, will_restart)."""
    ok, msg, changed = pull_ff_only()
    if ok and changed:
        return True, msg + "\nDang khoi dong lai listen...", True
    return ok, msg, False
