"""
listener.py - Vong lap chinh: lang nghe lenh Telegram (long polling) va
dong thoi tu kiem tra CPU/RAM de canh bao neu vuot nguong.
"""

import sys
import time
import signal
import threading
from collections import defaultdict

import requests

from . import config
from . import telegram_api
from . import commands
from . import system_info
from . import autostart
from . import updater

POLL_TIMEOUT_SEC = 30
RETRY_SLEEP_SEC = 10
MAX_INFLIGHT = 16
_EXCLUSIVE_GROUPS = {"vpn", "update", "service", "power"}
_group_locks = {name: threading.Lock() for name in _EXCLUSIVE_GROUPS}
_inflight_lock = threading.Lock()
_inflight = 0
_group_inflight: dict[str, int] = defaultdict(int)
_shutting_down = False


def _handle_termination_signal(signum, frame) -> None:
    """Tren macOS/Linux, he thong gui SIGTERM cho tien trinh truoc khi tat
    may / khoi dong lai / dang xuat. Bat tin hieu nay de bao qua Telegram
    TRUOC KHI tien trinh bi dung, tuong tu Event ID 1074 tren Windows."""
    global _shutting_down
    if autostart.takeover_requested():
        telegram_api.log(f"Nhan tin hieu {signum}: instance moi ghi de — thoat, khong gui shutdown.")
        raise SystemExit(0)
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


def _dec_inflight(group: str) -> None:
    global _inflight
    with _inflight_lock:
        _inflight = max(0, _inflight - 1)
        _group_inflight[group] = max(0, _group_inflight[group] - 1)


def _enqueue(kind: str, chat_id: str, fn) -> None:
    """Nhan lenh xong spawn thread ngay. Poll khong bao gio cho lenh truoc."""
    global _inflight
    group = commands.command_group(kind)
    meta = commands.GROUP_META[group]
    label = meta["label"]
    timeout_sec = int(meta["timeout"])

    with _inflight_lock:
        if _inflight >= MAX_INFLIGHT:
            waiting = _inflight
            busy = True
        else:
            waiting = _group_inflight[group]
            _group_inflight[group] += 1
            _inflight += 1
            busy = False

    if busy:
        threading.Thread(
            target=telegram_api.reply,
            args=(
                chat_id,
                f"[{label}] Dang co {waiting} lenh chay song song (toi da {MAX_INFLIGHT}). Gui lai sau. Lenh dang chay khong bi dung.",
            ),
            kwargs={"parse_mode": "", "timeout": 3},
            daemon=True,
        ).start()
        return

    def _job() -> None:
        exclusive = _group_locks.get(group)
        got_lock = True
        try:
            commands.send_loading(chat_id, kind, waiting)
            if exclusive:
                got_lock = exclusive.acquire(timeout=timeout_sec)
                if not got_lock:
                    telegram_api.reply(
                        chat_id,
                        f"[{label}] dang chay lenh truoc trong cung group. Group khac van nhan lenh. Gui lai {kind}.",
                        parse_mode="",
                        timeout=5,
                    )
                    return
            fn()
        except Exception as e:
            telegram_api.log(f"Job [{label}] {kind}: {e}")
            if chat_id:
                telegram_api.reply(
                    chat_id,
                    f"Loi [{label}] {kind}: {e}\nListen van dang chay. Lenh khac khong bi anh huong.",
                    parse_mode="",
                )
        finally:
            if exclusive and got_lock:
                exclusive.release()
            done.set()
            _dec_inflight(group)

    def _watchdog() -> None:
        if not done.wait(timeout_sec):
            telegram_api.log(f"Job [{label}] {kind} qua {timeout_sec}s (lenh khac van chay)")
            if chat_id:
                telegram_api.reply(
                    chat_id,
                    f"[{label}] {kind} chua xong sau {timeout_sec}s. Lenh khac van chay doc lap. Gui lai neu can.",
                    parse_mode="",
                    timeout=5,
                )

    done = threading.Event()
    threading.Thread(target=_job, daemon=True, name=f"{group}-{kind[:16]}").start()
    threading.Thread(target=_watchdog, daemon=True, name=f"wd-{group}").start()


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


def _auto_update_loop() -> None:
    if not config.ENABLE_AUTO_UPDATE or config.AUTO_UPDATE_MINUTES <= 0:
        return
    telegram_api.log(
        f"Auto-update: moi {config.AUTO_UPDATE_MINUTES} phut se git pull --ff-only."
    )
    time.sleep(180)
    interval = max(10, config.AUTO_UPDATE_MINUTES) * 60
    while True:
        try:
            ok, msg, will_restart = updater.apply_and_restart()
            if ok and will_restart:
                telegram_api.send_to_all(
                    "🔄 Phat hien code moi tren git. Dang restart listen..."
                )
                updater.spawn_new_listener()
            elif not ok:
                telegram_api.log(f"Auto-update: {msg}")
        except Exception as e:
            telegram_api.log(f"Auto-update loi: {e}")
        time.sleep(interval)


def _notify_service_ready() -> None:
    """Bao Telegram khi listener start — retry neu may moi boot, mang chua len.
    Bo qua neu task startup vua gui tin trong 2 phut (tranh 2 tin trung)."""
    manual = bool(getattr(sys.stdin, "isatty", lambda: False)())
    try:
        if config.UPDATE_STAMP_FILE.exists():
            raw = config.UPDATE_STAMP_FILE.read_text(encoding="utf-8").strip()
            parts = raw.split()
            kind = "update"
            ts = 0.0
            if len(parts) == 1:
                ts = float(parts[0])
            elif len(parts) >= 2:
                kind = parts[0]
                ts = float(parts[-1])
            if (time.time() - ts) < 180:
                if kind == "reload":
                    telegram_api.send_to_all(
                        "🔄 <b>DA RELOAD SERVICE</b>\n"
                        "Listen moi dang chay — gui /help, /vpn, /service de kiem tra."
                    )
                else:
                    telegram_api.send_to_all(
                        "🔄 <b>DA CAP NHAT CODE</b>\n"
                        "Listen moi dang chay — gui /help, /vpn, /service de kiem tra."
                    )
                try:
                    config.UPDATE_STAMP_FILE.unlink(missing_ok=True)
                except OSError:
                    pass
                telegram_api.mark_boot_notified()
                telegram_api.log(f"Da bao Telegram: {kind} xong.")
                return
    except Exception:
        pass
    if (not manual) and telegram_api.boot_notify_recently_sent(120):
        telegram_api.log("Bo qua thong bao ready: startup vua gui roi.")
        return
    text = commands.build_event_message("ready")
    if telegram_api.send_to_all_retry(text, attempts=12, delay_sec=10):
        telegram_api.mark_boot_notified()
        telegram_api.log("Da gui thong bao: may da bat, service san sang.")
    else:
        telegram_api.log("Khong gui duoc thong bao ready sau nhieu lan thu.")


def run() -> None:
    config.validate()
    autostart.mark_listener_role()
    telegram_api.log("Listener dang khoi dong...")
    try:
        takeover_note = autostart.takeover_existing_listener()
        telegram_api.log(f"Ghi de listen cu: {takeover_note}")
    except Exception as e:
        telegram_api.log(f"Bo qua ghi de listen cu: {e}")
    telegram_api.log(
        f"Listener bat dau chay. Chi tra loi chat_id trong: {config.ALLOWED_CHAT_IDS}"
    )
    try:
        refreshed = autostart.refresh_windows_startup()
        if refreshed:
            telegram_api.log(refreshed)
    except Exception as e:
        telegram_api.log(f"Khong cap nhat duoc Startup: {e}")
    telegram_api.clear_webhook()
    telegram_api.set_my_commands(commands.telegram_menu_commands())

    ready_thread = threading.Thread(target=_notify_service_ready, daemon=True)
    ready_thread.start()

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

    threading.Thread(target=_auto_update_loop, daemon=True).start()
    telegram_api.log("Lenh chay song song: moi event 1 thread, VPN/update/service chi xep hang trong group minh.")

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

        if not isinstance(result, dict) or not result.get("ok"):
            desc = str((result or {}).get("description") if isinstance(result, dict) else result)
            if "terminated by other getUpdates" in desc or "Conflict" in desc:
                telegram_api.log(
                    "Telegram Conflict: con listen khac cung BOT_TOKEN "
                    "(service an / terminal khac / may khac). Dang ghi de tren may nay..."
                )
                threading.Thread(
                    target=autostart.takeover_existing_listener,
                    daemon=True,
                    name="takeover",
                ).start()
            else:
                telegram_api.log(f"Telegram tra ve loi: {result}. Thu lai sau {RETRY_SLEEP_SEC}s")
            time.sleep(RETRY_SLEEP_SEC)
            continue

        for update in result.get("result", []):
            try:
                offset = update["update_id"] + 1
                _save_offset(offset)

                callback = update.get("callback_query")
                if callback:
                    cq_id = str(callback.get("id", ""))
                    msg = callback.get("message") or {}
                    chat = msg.get("chat") or callback.get("from") or {}
                    chat_id = str(chat.get("id", ""))
                    data = str(callback.get("data") or "")
                    threading.Thread(
                        target=telegram_api.answer_callback_query,
                        args=(cq_id, "Dang xu ly..."),
                        daemon=True,
                    ).start()
                    if chat_id not in config.ALLOWED_CHAT_IDS:
                        telegram_api.log(f"Bo qua callback tu chat_id khong duoc phep: {chat_id}")
                        continue
                    _enqueue(
                        f"nut:{data[:24]}",
                        chat_id,
                        lambda cid=chat_id, payload=data: commands.handle_callback(cid, payload),
                    )
                    continue

                message = update.get("message") or {}
                chat = message.get("chat") or {}
                text = (message.get("text") or "").strip()
                chat_id = str(chat.get("id", ""))

                if chat_id not in config.ALLOWED_CHAT_IDS:
                    telegram_api.log(f"Bo qua tin nhan tu chat_id khong duoc phep: {chat_id}")
                    continue

                if not text:
                    continue

                def _job(cid=chat_id, body=text):
                    handled = commands.dispatch(cid, body)
                    if not handled:
                        telegram_api.log(f"Lenh khong xac dinh tu {cid}: {body}")
                        if body.startswith("/"):
                            telegram_api.reply(
                                cid,
                                "Khong hieu lenh nay.\n\n" + commands.build_help_text(),
                                parse_mode="HTML",
                            )

                _enqueue(text.split()[0][:24], chat_id, _job)
            except Exception as e:
                telegram_api.log(f"Loi khi xu ly update: {e}")
                chat_id = ""
                try:
                    msg = (update.get("callback_query") or {}).get("message") or update.get("message") or {}
                    chat_id = str((msg.get("chat") or {}).get("id") or "")
                except Exception:
                    chat_id = ""
                if chat_id:
                    telegram_api.reply(
                        chat_id,
                        f"Loi khi xu ly lenh: {e}\nListen van dang chay.",
                        parse_mode="",
                    )
