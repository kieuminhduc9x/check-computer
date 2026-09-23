#!/usr/bin/env python3
"""
main.py - Diem vao chinh cua PC Monitor Pro.

Cach dung:
    python main.py startup      -> bao may vua BAT / dang nhap
    python main.py shutdown     -> bao may sap TAT / khoi dong lai
    python main.py heartbeat    -> bao may VAN DANG BAT (dinh ky)
    python main.py test         -> gui tin nhan thu de kiem tra cau hinh
    python main.py listen       -> chay nen lien tuc, lang nghe lenh Telegram
    python main.py listen-boot  -> listen truoc dang nhap (Task Scheduler goi, session he thong)
    python main.py hide         -> chay listen AN (pythonw), tra cua so ve ngay
    python main.py install      -> dang ky service (Windows tu hoi quyen Admin / UAC)
    python main.py uninstall    -> go bo service tu khoi dong
    python main.py service      -> xem service da dang ky chua
    python main.py reload       -> khoi dong lai listen (nap code, khong git pull)

Cau hinh trong file .env o cung thu muc voi main.py (xem .env.example).
"""

import sys

from pc_monitor import config
from pc_monitor import commands
from pc_monitor import telegram_api
from pc_monitor import listener
from pc_monitor import autostart
from pc_monitor import updater


def run_one_shot(event: str) -> None:
    config.validate()
    if event == "test":
        text = "✅ Ket noi Telegram bot thanh cong! PC Monitor Pro san sang su dung."
        attempts = 3
    else:
        text = commands.build_event_message(event)
        attempts = 12 if event in ("startup", "shutdown", "heartbeat") else 3

    ok = telegram_api.send_to_all_retry(text, attempts=attempts, delay_sec=8)
    if ok and event == "startup":
        telegram_api.mark_boot_notified()
    sys.exit(0 if ok else 1)


def main() -> None:
    valid = (
        "startup", "shutdown", "heartbeat", "test", "listen", "listen-boot", "hide",
        "install", "uninstall", "service", "reload",
    )
    if len(sys.argv) < 2 or sys.argv[1] not in valid:
        print(__doc__)
        sys.exit(1)

    event = sys.argv[1]
    if event in ("listen", "listen-boot"):
        listener.run()
    elif event == "hide":
        print("Bat listen an (pythonw). Co the dong Git Bash.", flush=True)
        updater.spawn_new_listener(notify_update=False)
    elif event == "reload":
        print("Reload listen...", flush=True)
        updater.spawn_new_listener(kind="reload")
    elif event in ("install", "uninstall", "service"):
        autostart.run_cli(event)
    else:
        run_one_shot(event)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        telegram_api.log("Ctrl+C: chuyen listen sang che do an (giong luc boot).")
        try:
            if len(sys.argv) > 1 and sys.argv[1] == "listen":
                updater.spawn_new_listener(notify_update=False)
        except Exception as e:
            telegram_api.log(f"Khong spawn duoc listen an: {e}")
    except Exception as e:
        try:
            telegram_api.log(f"Crash: {e}")
            telegram_api.send_to_all(
                f"Listen crash: {e}\nHay chay lai python main.py listen (hoac start-project).",
                parse_mode="",
            )
        except Exception:
            print(f"Crash: {e}", flush=True)
        raise
