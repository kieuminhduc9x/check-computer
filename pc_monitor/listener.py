"""
listener.py - Vong lap chinh: lang nghe lenh Telegram (long polling) va
dong thoi tu kiem tra CPU/RAM de canh bao neu vuot nguong.
"""

import time
import signal
import threading
import requests

from . import config
from . import telegram_api
from . import commands
from . import system_info

POLL_TIMEOUT_SEC = 30
RETRY_SLEEP_SEC = 10

_shutting_down = False


def _handle_termination_signal(signum, frame) -> None:
    """Tren macOS/Linux, he thong gui SIGTERM cho tien trinh truoc khi tat
    may / khoi dong lai / dang xuat. Bat tin hieu nay de bao qua Telegram
    TRUOC KHI tien trinh bi dung, tuong tu Event ID 1074 tren Windows."""
    global _shutting_down
    _shutting_down = True
    telegram_api.log(f"Nhan tin hieu dung (signal {signum}) -> gui thong bao shutdown")
    for chat_id in config.ALLOWED_CHAT_IDS:
        telegram_api.send_message(chat_id, commands.build_event_message("shutdown"))
    raise SystemExit(0)


def _load_offset() -> int:
    if config.OFFSET_FILE.exists():
        try:
            return int(config.OFFSET_FILE.read_text().strip())
        except Exception:
            return 0
    return 0


def _save_offset(offset: int) -> None:
    try:
        config.OFFSET_FILE.write_text(str(offset))
    except OSError:
        pass


def _alert_watcher_loop() -> None:
    """Chay trong thread rieng: kiem tra CPU/RAM dinh ky, canh bao neu vuot
    nguong lien tuc nhieu lan (tranh bao nham do tang dot ngot)."""
    if config.ALERT_CPU_PERCENT <= 0 and config.ALERT_RAM_PERCENT <= 0:
        return  # tinh nang tat

    cpu_streak = 0
    ram_streak = 0
    cpu_alerted = False
    ram_alerted = False

    while True:
        try:
            cpu, ram = system_info.get_cpu_ram_percent()

            if config.ALERT_CPU_PERCENT > 0:
                if cpu >= config.ALERT_CPU_PERCENT:
                    cpu_streak += 1
                else:
                    cpu_streak = 0
                    cpu_alerted = False
                if cpu_streak >= config.ALERT_CONSECUTIVE_CHECKS and not cpu_alerted:
                    for chat_id in config.ALLOWED_CHAT_IDS:
                        telegram_api.send_message(
                            chat_id,
                            f"⚠️ <b>CANH BAO CPU CAO</b>\n{config.COMPUTER_NAME}: CPU dang o {cpu}% "
                            f"(vuot nguong {config.ALERT_CPU_PERCENT}%)",
                        )
                    cpu_alerted = True

            if config.ALERT_RAM_PERCENT > 0:
                if ram >= config.ALERT_RAM_PERCENT:
                    ram_streak += 1
                else:
                    ram_streak = 0
                    ram_alerted = False
                if ram_streak >= config.ALERT_CONSECUTIVE_CHECKS and not ram_alerted:
                    for chat_id in config.ALLOWED_CHAT_IDS:
                        telegram_api.send_message(
                            chat_id,
                            f"⚠️ <b>CANH BAO RAM CAO</b>\n{config.COMPUTER_NAME}: RAM dang o {ram}% "
                            f"(vuot nguong {config.ALERT_RAM_PERCENT}%)",
                        )
                    ram_alerted = True

        except Exception as e:
            telegram_api.log(f"Loi trong luong canh bao CPU/RAM: {e}")

        time.sleep(config.ALERT_CHECK_INTERVAL_SECONDS)


def run() -> None:
    config.validate()
    telegram_api.log(
        f"Listener bat dau chay. Chi tra loi chat_id trong: {config.ALLOWED_CHAT_IDS}"
    )

    # Bat tin hieu tat/khoi dong lai tren macOS & Linux (Windows dung
    # Event ID 1074 rieng, xem scripts/windows/). signal.SIGTERM khong ton
    # tai tren mot so he thong -> bo qua neu khong ho tro.
    try:
        signal.signal(signal.SIGTERM, _handle_termination_signal)
    except (AttributeError, ValueError):
        pass

    if config.ALERT_CPU_PERCENT > 0 or config.ALERT_RAM_PERCENT > 0:
        t = threading.Thread(target=_alert_watcher_loop, daemon=True)
        t.start()
        telegram_api.log(
            f"Da bat canh bao: CPU>={config.ALERT_CPU_PERCENT}% RAM>={config.ALERT_RAM_PERCENT}%"
        )

    offset = _load_offset()

    while True:
        try:
            result = telegram_api.get_updates(offset, POLL_TIMEOUT_SEC)
        except requests.RequestException as e:
            telegram_api.log(f"Mat ket noi mang, thu lai sau {RETRY_SLEEP_SEC}s: {e}")
            time.sleep(RETRY_SLEEP_SEC)
            continue
        except Exception as e:
            telegram_api.log(f"Loi khong xac dinh, thu lai sau {RETRY_SLEEP_SEC}s: {e}")
            time.sleep(RETRY_SLEEP_SEC)
            continue

        if not result.get("ok"):
            telegram_api.log(f"Telegram tra ve loi: {result}. Thu lai sau {RETRY_SLEEP_SEC}s")
            time.sleep(RETRY_SLEEP_SEC)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1
            _save_offset(offset)

            message = update.get("message") or {}
            chat = message.get("chat") or {}
            text = (message.get("text") or "").strip()
            chat_id = str(chat.get("id", ""))

            if chat_id not in config.ALLOWED_CHAT_IDS:
                telegram_api.log(f"Bo qua tin nhan tu chat_id khong duoc phep: {chat_id}")
                continue

            if not text:
                continue

            handled = commands.dispatch(chat_id, text)
            if not handled:
                telegram_api.log(f"Lenh khong xac dinh tu {chat_id}: {text}")
