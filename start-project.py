#!/usr/bin/env python3
"""
start-project.py - 1 lenh sau khi clone tren may moi (Windows / macOS / Linux).

    python3 start-project.py
    py start-project.py

Lam: tao .venv, pip install, tao .env neu chua co, dang ky autostart, bat listen an.
Lan sau chi git pull (hoac /update). Khong commit file .env.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
ENV_PATH = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"
REQ = ROOT / "requirements.txt"


def _configure_stdio() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if os.name != "nt":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


def log(msg: str) -> None:
    text = str(msg)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    log("> " + " ".join(cmd))
    return subprocess.run(cmd, cwd=str(ROOT), **kwargs)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def ensure_venv() -> Path:
    py = venv_python()
    if py.exists():
        log(f"Dung venv san co: {py}")
        return py
    log("Tao virtualenv .venv ...")
    r = run([sys.executable, "-m", "venv", str(VENV)])
    if r.returncode != 0:
        sys.exit("Khong tao duoc .venv. Can Python 3.10+ (python.org / py -3).")
    py = venv_python()
    if not py.exists():
        sys.exit("venv tao xong nhung khong thay python trong .venv.")
    return py


def pip_install(py: Path) -> None:
    log("Cai thu vien (requirements.txt) ...")
    r = run([str(py), "-m", "pip", "install", "--upgrade", "pip"], timeout=180)
    if r.returncode != 0:
        log("Canh bao: khong upgrade duoc pip, van thu install.")
    r = run([str(py), "-m", "pip", "install", "-r", str(REQ)], timeout=300)
    if r.returncode != 0:
        sys.exit("pip install that bai.")


def env_placeholder(text: str) -> bool:
    return (
        "DAN_BOT_TOKEN" in text
        or "DAN_CHAT_ID" in text
        or "BOT_TOKEN=" in text and "BOT_TOKEN=DAN_" in text
    )


def ensure_env() -> bool:
    """True neu .env da dien token. False neu can user sua roi chay lai."""
    if not ENV_PATH.exists():
        if not EXAMPLE.exists():
            sys.exit("Thieu .env.example")
        shutil.copy(EXAMPLE, ENV_PATH)
        host = platform.node() or "May-Moi"
        text = ENV_PATH.read_text(encoding="utf-8")
        text = text.replace("COMPUTER_NAME=May-Tinh-Cua-Toi", f"COMPUTER_NAME={host}")
        ENV_PATH.write_text(text, encoding="utf-8")
        log(f"Da tao .env (ten may: {host}).")
    text = ENV_PATH.read_text(encoding="utf-8")
    if env_placeholder(text):
        log("")
        log("============================================================")
        log("Mo file .env va dien BOT_TOKEN + ALLOWED_CHAT_IDS")
        log(f"  {ENV_PATH}")
        log("Roi chay LAI:  python3 start-project.py   (hoac py start-project.py)")
        log("============================================================")
        if os.name == "nt":
            try:
                os.startfile(str(ENV_PATH))  # type: ignore[attr-defined]
            except Exception:
                pass
        return False
    return True


def main() -> None:
    _configure_stdio()
    os.chdir(ROOT)
    log(f"PC Monitor Pro — start-project")
    log(f"Thu muc: {ROOT}")
    log(f"OS: {platform.system()} {platform.release()}")
    if sys.version_info < (3, 10):
        sys.exit("Can Python 3.10 tro len.")

    py = ensure_venv()
    pip_install(py)
    if not ensure_env():
        sys.exit(2)

    log("Dang ky autostart (Windows co the hoi UAC — bam Yes) ...")
    inst = run([str(py), str(ROOT / "main.py"), "install"])
    if inst.returncode != 0:
        log("install chua xong (UAC / quyen). Van thu bat listen an.")

    log("Bat listen an ...")
    hide = run([str(py), str(ROOT / "main.py"), "hide"])
    if hide.returncode != 0:
        log("hide that bai — thu:  .venv/.../python main.py listen")
        sys.exit(1)

    log("")
    log("Xong. Listen dang chay an. Gui /status tren Telegram.")
    log("Lan sau: git pull  hoac  /update  — khong can start-project lai")
    log("         (tru khi doi requirements.txt thi chay lai start-project).")


if __name__ == "__main__":
    _configure_stdio()
    try:
        main()
    except KeyboardInterrupt:
        log("Da huy.")
        sys.exit(130)
