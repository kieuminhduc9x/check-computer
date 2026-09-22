"""
config.py - Doc cau hinh tu file .env nam o thu muc goc project.

Tat ca cac module khac import tu day de lay cau hinh, khong module nao tu
doc .env rieng, tranh sai lech.
"""

import os
import sys
import platform
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("LOI: chua cai thu vien python-dotenv.")
    print("Chay: pip install -r requirements.txt")
    sys.exit(1)

# Thu muc goc cua project (noi chua file .env, main.py, requirements.txt)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

if not ENV_PATH.exists():
    print(f"LOI: khong tim thay file .env tai {ENV_PATH}")
    print("Hay copy .env.example thanh .env va dien thong tin cua ban.")
    sys.exit(1)

load_dotenv(ENV_PATH)


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

_raw_chat_ids = os.getenv("ALLOWED_CHAT_IDS", "").strip()
ALLOWED_CHAT_IDS = [c.strip() for c in _raw_chat_ids.split(",") if c.strip()]

COMPUTER_NAME = os.getenv("COMPUTER_NAME", "").strip() or platform.node()
HEARTBEAT_MINUTES = _get_int("HEARTBEAT_MINUTES", 60)

ALERT_CPU_PERCENT = _get_int("ALERT_CPU_PERCENT", 0)
ALERT_RAM_PERCENT = _get_int("ALERT_RAM_PERCENT", 0)
ALERT_CONSECUTIVE_CHECKS = max(1, _get_int("ALERT_CONSECUTIVE_CHECKS", 3))
ALERT_CHECK_INTERVAL_SECONDS = max(10, _get_int("ALERT_CHECK_INTERVAL_SECONDS", 60))

ENABLE_SCREENSHOT = _get_bool("ENABLE_SCREENSHOT", True)
ENABLE_LOCK = _get_bool("ENABLE_LOCK", True)
ENABLE_SHUTDOWN_RESTART = _get_bool("ENABLE_SHUTDOWN_RESTART", True)
ENABLE_NOTE = _get_bool("ENABLE_NOTE", True)
ENABLE_AUTOSTART = _get_bool("ENABLE_AUTOSTART", True)

NOTE_FILE = PROJECT_ROOT / os.getenv("NOTE_FILE", "notes.txt")
LOG_FILE = PROJECT_ROOT / "pc_monitor.log"
OFFSET_FILE = PROJECT_ROOT / ".update_offset"
SCREENSHOT_TMP = PROJECT_ROOT / ".last_screenshot.png"
READY_STAMP_FILE = PROJECT_ROOT / ".last_ready_notify"
LISTENER_PID_FILE = PROJECT_ROOT / ".listener.pid"
TAKEOVER_FILE = PROJECT_ROOT / ".listener.takeover"


def validate(exit_on_error: bool = True) -> list:
    """Kiem tra cau hinh bat buoc. Tra ve danh sach loi (rong neu ok)."""
    errors = []
    if not BOT_TOKEN or BOT_TOKEN.startswith("DAN_"):
        errors.append("BOT_TOKEN chua duoc dien dung trong .env")
    if not ALLOWED_CHAT_IDS or any(c.startswith("DAN_") for c in ALLOWED_CHAT_IDS):
        errors.append("ALLOWED_CHAT_IDS chua duoc dien dung trong .env")

    if errors and exit_on_error:
        for e in errors:
            print(f"LOI CAU HINH: {e}")
        print(f"Hay mo file {ENV_PATH} va sua lai cho dung.")
        sys.exit(1)
    return errors
