#!/usr/bin/env python3
"""
main.py - Diem vao chinh cua PC Monitor Pro.

Cach dung:
    python main.py startup      -> bao may vua BAT / dang nhap
    python main.py shutdown     -> bao may sap TAT / khoi dong lai
    python main.py heartbeat    -> bao may VAN DANG BAT (dinh ky)
    python main.py test         -> gui tin nhan thu de kiem tra cau hinh
    python main.py listen       -> chay nen lien tuc, lang nghe lenh Telegram
    python main.py install      -> dang ky service (Windows tu hoi quyen Admin / UAC)
    python main.py uninstall    -> go bo service tu khoi dong
    python main.py service      -> xem service da dang ky chua

Cau hinh trong file .env o cung thu muc voi main.py (xem .env.example).
"""

import sys

from pc_monitor import config
from pc_monitor import commands
from pc_monitor import telegram_api
from pc_monitor import listener
from pc_monitor import autostart


def run_one_shot(event: str) -> None:
    config.validate()
    if event == "test":
        text = "✅ Ket noi Telegram bot thanh cong! PC Monitor Pro san sang su dung."
    else:
        text = commands.build_event_message(event)

    ok_all = True
    for chat_id in config.ALLOWED_CHAT_IDS:
        ok = telegram_api.send_message(chat_id, text)
        ok_all = ok_all and ok
    sys.exit(0 if ok_all else 1)


def main() -> None:
    valid = (
        "startup", "shutdown", "heartbeat", "test", "listen",
        "install", "uninstall", "service",
    )
    if len(sys.argv) < 2 or sys.argv[1] not in valid:
        print(__doc__)
        sys.exit(1)

    event = sys.argv[1]
    if event == "listen":
        listener.run()
    elif event in ("install", "uninstall", "service"):
        autostart.run_cli(event)
    else:
        run_one_shot(event)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        telegram_api.log("Da dung (Ctrl+C).")
    except Exception as e:
        try:
            telegram_api.log(f"Crash: {e}")
        except Exception:
            print(f"Crash: {e}", flush=True)
        raise
