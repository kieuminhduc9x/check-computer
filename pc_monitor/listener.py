"""
listener.py - Vong lap chinh: lang nghe lenh Telegram (long polling) va
dong thoi tu kiem tra CPU/RAM de canh bao neu vuot nguong.
"""

import json
import sys
import time
import signal
import threading
from collections import defaultdict
from pathlib import Path

import requests

from . import config
from . import telegram_api
from . import commands
from . import system_info
from . import autostart
from . import updater

PENDING_FILE = config.PROJECT_ROOT / ".pending_commands"

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


def wait_other_jobs(timeout: float = 8) -> None:
    """Cho lenh khac gui xong tin truoc khi /update /reload thoat process."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _inflight_lock:
            n = _inflight
        if n <= 1:
            return
        time.sleep(0.2)


def _pending_load() -> list[dict]:
    try:
        raw = Path(PENDING_FILE).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _pending_save(items: list[dict]) -> None:
    try:
        Path(PENDING_FILE).write_text(
            json.dumps(items[-40:], ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def _pending_add(uid: int, chat_id: str, text: str) -> None:
    items = [x for x in _pending_load() if x.get("uid") != uid]
    items.append({"uid": uid, "chat_id": chat_id, "text": text, "ts": time.time()})
    _pending_save(items)


def _pending_done(uid: int) -> None:
    _pending_save([x for x in _pending_load() if x.get("uid") != uid])


def _notify_orphaned_commands() -> None:
    items = _pending_load()
    _pending_save([])
    now = time.time()
    for item in items:
        try:
            if now - float(item.get("ts") or 0) > 180:
                continue
            chat_id = str(item.get("chat_id") or "")
            text = str(item.get("text") or "/lenh").split()[0][:40]
            if chat_id not in config.ALLOWED_CHAT_IDS:
                continue
            telegram_api.reply(
                chat_id,
                f"Listen bi gian doan khi dang xu ly {text}.\n"
                "PC van online. Gui lai lenh do.",
                parse_mode="",
            )
        except Exception:
            continue


def _enqueue(
    kind: str,
    chat_id: str,
    fn,
    *,
    reply_to: int = 0,
    uid: int = 0,
) -> None:
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
        if uid:
            _pending_done(uid)
        return

    def _job() -> None:
        exclusive = _group_locks.get(group)
        got_lock = False
        started = time.monotonic()
        try:
            mid = commands.send_tracker(chat_id, kind, waiting, reply_to=reply_to)
            box["mid"] = mid
            if exclusive:
                got_lock = exclusive.acquire(blocking=False)
                if not got_lock:
                    commands.finish_tracker(
                        chat_id,
                        mid,
                        kind,
                        "waiting",
                        elapsed=time.monotonic() - started,
                        reply_to=reply_to,
                    )
                    got_lock = exclusive.acquire(timeout=timeout_sec)
                    if not got_lock:
                        box["status"] = "err"
                        box["err"] = (
                            f"Group {label} dang chay lenh truoc. "
                            f"Group khac van nhan lenh. Gui lai {kind}."
                        )
                        return
                    commands.finish_tracker(
                        chat_id, mid, kind, "received", reply_to=reply_to
                    )
            fn()
            box["status"] = "ok"
        except Exception as e:
            box["status"] = "err"
            box["err"] = e
            telegram_api.log(f"Job [{label}] {kind}: {e}")
        finally:
            if exclusive and got_lock:
                exclusive.release()
            elapsed = time.monotonic() - started
            if box["status"] == "ok":
                commands.finish_tracker(
                    chat_id,
                    box.get("mid") or 0,
                    kind,
                    "ok",
                    elapsed=elapsed,
                    reply_to=reply_to,
                )
            elif box["status"] == "err":
                commands.finish_tracker(
                    chat_id,
                    box.get("mid") or 0,
                    kind,
                    "err",
                    elapsed=elapsed,
                    err=str(box.get("err") or "loi"),
                    reply_to=reply_to,
                )
            if uid:
                _pending_done(uid)
            done.set()
            _dec_inflight(group)

    def _watchdog() -> None:
        if not done.wait(timeout_sec):
            telegram_api.log(f"Job [{label}] {kind} qua {timeout_sec}s (lenh khac van chay)")
            if box["status"] not in ("ok", "err"):
                commands.finish_tracker(
                    chat_id,
                    box.get("mid") or 0,
                    kind,
                    "timeout",
                    timeout_sec=timeout_sec,
                    reply_to=reply_to,
                )

    box: dict = {"mid": 0, "status": "pending", "err": None}
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
    try:
        _notify_orphaned_commands()
    except Exception as e:
        telegram_api.log(f"Bo qua pending cu: {e}")

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
                try:
                    autostart.takeover_existing_listener()
                except Exception as e:
                    telegram_api.log(f"Takeover that bai: {e}")
                time.sleep(2)
            else:
                telegram_api.log(f"Telegram tra ve loi: {result}. Thu lai sau {RETRY_SLEEP_SEC}s")
                time.sleep(RETRY_SLEEP_SEC)
            continue

        for update in result.get("result", []):
            try:
                update_id = int(update["update_id"])
                offset = update_id + 1

                callback = update.get("callback_query")
                if callback:
                    cq_id = str(callback.get("id", ""))
                    msg = callback.get("message") or {}
                    chat = msg.get("chat") or callback.get("from") or {}
                    chat_id = str(chat.get("id", ""))
                    data = str(callback.get("data") or "")
                    reply_to = int(msg.get("message_id") or 0)
                    threading.Thread(
                        target=telegram_api.answer_callback_query,
                        args=(cq_id, "Dang xu ly..."),
                        daemon=True,
                    ).start()
                    if chat_id not in config.ALLOWED_CHAT_IDS:
                        telegram_api.log(f"Bo qua callback tu chat_id khong duoc phep: {chat_id}")
                        _save_offset(offset)
                        continue
                    telegram_api.log(f"Nhan nut {data[:40]} tu {chat_id}")
                    _pending_add(update_id, chat_id, f"nut:{data[:24]}")
                    _save_offset(offset)
                    _enqueue(
                        f"nut:{data[:24]}",
                        chat_id,
                        lambda cid=chat_id, payload=data: commands.handle_callback(cid, payload),
                        reply_to=reply_to,
                        uid=update_id,
                    )
                    continue

                message = update.get("message") or {}
                chat = message.get("chat") or {}
                text = (message.get("text") or "").strip()
                chat_id = str(chat.get("id", ""))
                reply_to = int(message.get("message_id") or 0)

                if chat_id not in config.ALLOWED_CHAT_IDS:
                    telegram_api.log(f"Bo qua tin nhan tu chat_id khong duoc phep: {chat_id}")
                    _save_offset(offset)
                    continue

                if not text:
                    _save_offset(offset)
                    continue

                telegram_api.log(f"Nhan {text.split()[0][:40]} tu {chat_id}")
                _pending_add(update_id, chat_id, text)
                _save_offset(offset)

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

                _enqueue(
                    text.split()[0][:24],
                    chat_id,
                    _job,
                    reply_to=reply_to,
                    uid=update_id,
                )
            except Exception as e:
                telegram_api.log(f"Loi khi xu ly update: {e}")
                try:
                    _save_offset(int(update.get("update_id") or 0) + 1)
                except Exception:
                    pass
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
