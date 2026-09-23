"""
commands.py - Noi dung tin nhan va bang dieu phoi lenh Telegram.

Moi lenh la 1 ham nhan (chat_id) va tu gui phan hoi qua telegram_api.
Lenh nguy hiem (tat may / khoi dong lai) can xac nhan 2 buoc trong vong 30s.
"""

from __future__ import annotations

import time
import threading
from datetime import datetime
from pathlib import Path
import platform

from . import config
from . import system_info
from . import actions
from . import telegram_api
from . import autostart
from . import vpn
from . import updater

# chat_id -> {"action": "shutdown"|"restart", "expires_at": float}
_pending_confirmations = {}
CONFIRM_TIMEOUT_SECONDS = 90
_BG_SLOTS = threading.Semaphore(2)

GROUP_META = {
    "info": {"label": "Trang thai", "timeout": 45, "maxsize": 12},
    "screen": {"label": "Chup man hinh", "timeout": 70, "maxsize": 8},
    "apps": {"label": "Ung dung", "timeout": 45, "maxsize": 8},
    "vpn": {"label": "VPN", "timeout": 90, "maxsize": 8},
    "power": {"label": "Tat/khoi dong", "timeout": 30, "maxsize": 4},
    "service": {"label": "Service", "timeout": 60, "maxsize": 4},
    "update": {"label": "Cap nhat", "timeout": 90, "maxsize": 2},
    "note": {"label": "Ghi chu", "timeout": 20, "maxsize": 8},
    "menu": {"label": "Menu", "timeout": 20, "maxsize": 8},
}

_LOADING = {
    "status": "dang lay trang thai may",
    "ping": "dang kiem tra may con online",
    "help": "dang lay danh sach lenh",
    "start": "dang lay danh sach lenh",
    "cpu": "dang do CPU",
    "ram": "dang do RAM",
    "disk": "dang do o dia",
    "procs": "dang liet ke tien trinh",
    "apps": "dang liet ke ung dung dang mo",
    "windows": "dang liet ke cua so",
    "software": "dang liet ke phan mem da cai",
    "installed": "dang liet ke phan mem da cai",
    "programs": "dang liet ke phan mem da cai",
    "open": "dang mo ung dung",
    "run": "dang mo ung dung",
    "ip": "dang lay dia chi IP",
    "screenshot": "dang chup man hinh",
    "lock": "dang khoa man hinh",
    "close_apps": "dang chuan bi tat het ung dung",
    "close": "dang tat 1 ung dung",
    "confirm_close_apps": "dang tat ung dung",
    "vpn": "dang doc profile Pritunl",
    "vpn_list": "dang doc profile Pritunl",
    "vpn_on": "dang bat VPN",
    "vpn_off": "dang tat VPN",
    "vpn_on_all": "dang bat tat ca VPN",
    "vpn_off_all": "dang tat tat ca VPN",
    "note": "dang luu ghi chu",
    "autostart": "dang kiem tra / cai autostart",
    "autostart_off": "dang go autostart",
    "service": "dang kiem tra service khoi dong",
    "svc": "dang kiem tra service khoi dong",
    "reload": "dang reload listen",
    "service_reload": "dang reload listen",
    "update": "dang git pull va cap nhat",
    "shutdown_now": "dang tao xac nhan tat may",
    "restart_now": "dang tao xac nhan khoi dong lai",
    "confirm_shutdown": "dang gui lenh tat may",
    "confirm_restart": "dang gui lenh khoi dong lai",
    "cancel_power": "dang huy lenh",
}


def _norm_loading_key(kind: str) -> str:
    key = (kind or "").strip().lower().split("@")[0]
    if key.startswith("nut:"):
        key = key[4:]
    if key.startswith("/"):
        key = key[1:]
    key = key.split()[0] if key else ""
    if key.startswith("vpn_on"):
        return "vpn_on_all" if key in ("vpn_on_all", "vpn_on:all") else "vpn_on"
    if key.startswith("vpn_off"):
        return "vpn_off_all" if key in ("vpn_off_all", "vpn_off:all") else "vpn_off"
    if key.startswith("confirm_shutdown"):
        return "confirm_shutdown"
    if key.startswith("confirm_restart"):
        return "confirm_restart"
    if key.startswith("o:"):
        return "open"
    if key.startswith("c:"):
        return "close"
    if key.startswith("confirm_close"):
        return "confirm_close_apps"
    return key


def command_group(kind: str) -> str:
    """Gan lenh vao 1 group de chay doc lap, khong chan group khac."""
    key = _norm_loading_key(kind)
    if key.startswith("vpn"):
        return "vpn"
    if key.startswith("screenshot"):
        return "screen"
    if key.startswith(("apps", "windows", "close", "lock", "confirm_close", "software", "installed", "programs", "open", "run")):
        return "apps"
    if key.startswith((
        "shutdown",
        "restart",
        "confirm_shutdown",
        "confirm_restart",
        "cancel_power",
    )):
        return "power"
    if key.startswith(("autostart", "service", "svc", "reload")):
        return "service"
    if key.startswith("update"):
        return "update"
    if key.startswith("note"):
        return "note"
    if key.startswith(("help", "start")):
        return "menu"
    if key.startswith(("status", "ping", "cpu", "ram", "disk", "procs", "ip")):
        return "info"
    return "menu"


def group_label(kind: str) -> str:
    return GROUP_META[command_group(kind)]["label"]


def _cmd_display(kind: str) -> str:
    key = _norm_loading_key(kind)
    if not key:
        return kind or "lenh"
    if kind.lower().startswith("nut:"):
        return key
    return f"/{key}"


def tracker_text(
    kind: str,
    state: str,
    waiting: int = 0,
    elapsed: float = 0,
    err: str | None = None,
    timeout_sec: int = 0,
) -> str:
    label = group_label(kind)
    cmd = _cmd_display(kind)
    key = _norm_loading_key(kind)
    action = _LOADING.get(key) or f"dang xu ly {cmd}"
    if state == "received":
        line = f"[{label}] PC DA NHAN {cmd}\nDang: {action}..."
        if waiting > 0:
            line += f"\nHang doi {label}: {waiting} lenh truoc."
        return line
    if state == "waiting":
        return f"[{label}] PC DA NHAN {cmd}\nDang cho lenh {label} truoc xong..."
    if state == "timeout":
        return (
            f"[{label}] {cmd} CHUA XONG sau {timeout_sec}s\n"
            "PC van dang chay. Tin nay se doi thanh XONG/LOI khi ket thuc."
        )
    if state == "err":
        detail = (str(err)[:300] if err else "loi khong ro")
        return f"[{label}] {cmd} LOI ({elapsed:.0f}s)\n{detail}"
    return f"[{label}] {cmd} XONG ({elapsed:.0f}s)"


def send_tracker(
    chat_id: str,
    kind: str,
    waiting: int = 0,
    reply_to: int = 0,
) -> int:
    """Tin vong doi: PC da nhan. Tra ve message_id de sua thanh XONG/LOI."""
    text = tracker_text(kind, "received", waiting=waiting)
    for attempt in range(8):
        mid = telegram_api.send_plain(
            chat_id, text, timeout=10, reply_to_message_id=reply_to
        )
        if mid:
            return mid
        time.sleep(0.6 * (attempt + 1))
    telegram_api.log(f"Khong gui duoc tracker {kind} toi {chat_id}")
    return 0


def finish_tracker(
    chat_id: str,
    message_id: int,
    kind: str,
    state: str,
    elapsed: float = 0,
    err: str | None = None,
    timeout_sec: int = 0,
    reply_to: int = 0,
) -> None:
    text = tracker_text(
        kind,
        state,
        elapsed=elapsed,
        err=err,
        timeout_sec=timeout_sec,
    )
    if message_id and telegram_api.edit_message(chat_id, message_id, text, timeout=8):
        return
    for attempt in range(5):
        mid = telegram_api.send_plain(
            chat_id, text, timeout=10, reply_to_message_id=reply_to
        )
        if mid:
            return
        time.sleep(0.6 * (attempt + 1))
    telegram_api.log(f"Khong gui duoc ket qua tracker {kind} toi {chat_id}")


def send_loading(chat_id: str, kind: str, waiting: int = 0) -> bool:
    return bool(send_tracker(chat_id, kind, waiting))


def _reply(chat_id: str, text: str, parse_mode: str = "HTML", reply_markup: dict | None = None) -> bool:
    return telegram_api.reply(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)


def _bg(chat_id: str, label: str, fn) -> None:
    """Chay lenh lau trong thread; toi da 2 lenh nen cung luc, loi van gui Telegram."""

    def _run() -> None:
        got = _BG_SLOTS.acquire(timeout=45)
        if not got:
            telegram_api.reply(
                chat_id,
                f"{label} cho qua lau (dang co lenh nen khac). Gui lai sau.",
                parse_mode="",
            )
            return
        try:
            fn()
        except Exception as e:
            telegram_api.log(f"{label}: {e}")
            telegram_api.reply(
                chat_id,
                f"Loi {label}: {e}\nListen van dang chay.",
                parse_mode="",
            )
        finally:
            _BG_SLOTS.release()

    threading.Thread(target=_run, daemon=True).start()


# --------------------------- Noi dung tin nhan dung chung ---------------------

def build_event_message(event: str) -> str:
    now_str = datetime.now().strftime("%H:%M:%S ngay %d/%m/%Y")
    host = system_info.get_hostname()
    ip = system_info.get_local_ip()

    titles = {
        "startup": "🟢 MAY TINH DA BAT",
        "ready": "🟢 MAY TINH DA BAT — SERVICE DA SAN SANG",
        "shutdown": "🔴 MAY TINH SAP TAT / KHOI DONG LAI",
        "heartbeat": "💚 MAY TINH VAN DANG HOAT DONG",
    }
    title = titles.get(event, "ℹ️ THONG BAO TU MAY TINH")
    extra = ""
    if event in ("startup", "ready"):
        extra = f"\nDa bat lien tuc: {system_info.get_uptime_str()}"
    if event == "ready":
        extra += (
            "\nListener ban day du — gui /status, /service, /autostart, /help."
        )

    return (
        f"<b>{title}</b>\n"
        f"Ten may: {config.COMPUTER_NAME} ({host})\n"
        f"IP noi bo: {ip}\n"
        f"Thoi gian: {now_str}{extra}"
    )


def build_status_text() -> str:
    return system_info.get_status_overview_text(config.COMPUTER_NAME)


def _disabled_suffix(enabled: bool) -> str:
    return "" if enabled else "  — dang tat trong .env"


def build_help_text() -> str:
    lines = [
        "🤖 <b>Danh sach lenh</b>",
        "Moi lenh 1 thread: screenshot chay song song voi VPN/status. Chi VPN/update/service xep hang trong group minh.",
        "",
        "<b>[Trang thai]</b>",
        "/status — may dang bat, CPU/RAM, app dang dung, app dang mo",
        "/ping — giong /status, dung de hoi may con online khong",
        "/cpu — % CPU",
        "/ram — % RAM",
        "/disk — dung luong o dia",
        "/procs — top 5 tien trinh ngon CPU",
        "/ip — IP noi bo va IP cong khai",
        "",
        "<b>[Chup man hinh]</b>",
        f"/screenshot — chup man hinh{_disabled_suffix(config.ENABLE_SCREENSHOT)}",
        "",
        "<b>[Ung dung]</b>",
        "/apps — danh sach ung dung / cua so dang mo",
        "/windows — giong /apps",
        "/software — phan mem da cai tren may (loc: /software chrome)",
        "/installed — giong /software",
        f"/open chrome — mo 1 app da cai{_disabled_suffix(config.ENABLE_OPEN_APPS)}",
        f"/lock — khoa man hinh{_disabled_suffix(config.ENABLE_LOCK)}",
        f"/close chrome — tat 1 app dang mo{_disabled_suffix(config.ENABLE_CLOSE_APPS)}",
        f"/close_apps — tat het ung dung dang mo, can xac nhan{_disabled_suffix(config.ENABLE_CLOSE_APPS)}",
        "",
        "<b>[VPN]</b>",
        f"/vpn — danh sach profile Pritunl, nut bat/tat{_disabled_suffix(config.ENABLE_VPN)}",
        f"/vpn_on — bat tat ca profile chua ket noi{_disabled_suffix(config.ENABLE_VPN)}",
        f"/vpn_off — tat tat ca profile dang ket noi{_disabled_suffix(config.ENABLE_VPN)}",
        "",
        "<b>[Tat/khoi dong]</b>",
        f"/shutdown_now — tat may, can xac nhan (ca khi khoa man hinh){_disabled_suffix(config.ENABLE_SHUTDOWN_RESTART)}",
        f"/restart_now — khoi dong lai, can xac nhan{_disabled_suffix(config.ENABLE_SHUTDOWN_RESTART)}",
        f"/confirm_shutdown — xac nhan tat may{_disabled_suffix(config.ENABLE_SHUTDOWN_RESTART)}",
        f"/confirm_restart — xac nhan khoi dong lai{_disabled_suffix(config.ENABLE_SHUTDOWN_RESTART)}",
        "",
        "<b>[Ghi chu]</b>",
        f"/note noi dung — luu ghi chu vao may{_disabled_suffix(config.ENABLE_NOTE)}",
        "",
        "<b>[Service]</b>",
        f"/autostart — dang ky chay khi khoi dong may{_disabled_suffix(config.ENABLE_AUTOSTART)}",
        f"/autostart_off — go bo service khoi dong{_disabled_suffix(config.ENABLE_AUTOSTART)}",
        f"/service — xem service khoi dong da cai chua{_disabled_suffix(config.ENABLE_AUTOSTART)}",
        "/reload — khoi dong lai listen (nap code, khong git pull)",
        "/service reload — giong /reload",
        "",
        "<b>[Cap nhat]</b>",
        f"/update — git pull va restart listen{_disabled_suffix(config.ENABLE_AUTO_UPDATE)}",
        "",
        "<b>[Menu]</b>",
        "/help — xem lai danh sach nay",
        "",
        "Tin tracker: PC DA NHAN -> XONG / LOI / CHUA XONG. Biet lenh da toi may va khi nao ket thuc.",
        "Neu may da tat, moi lenh se khong co phan hoi.",
    ]
    return "\n".join(lines)


def telegram_menu_commands() -> list:
    """Danh sach dang ky vao nut '/' tren Telegram (toi da 100 lenh)."""
    items = [
        ("status", "[Trang thai] CPU/RAM, app dang mo"),
        ("ping", "[Trang thai] Kiem tra may con online"),
        ("cpu", "[Trang thai] Phan tram CPU"),
        ("ram", "[Trang thai] Phan tram RAM"),
        ("disk", "[Trang thai] Dung luong o dia"),
        ("procs", "[Trang thai] Top tien trinh theo CPU"),
        ("ip", "[Trang thai] IP noi bo va cong khai"),
        ("apps", "[Ung dung] Cua so dang mo"),
        ("windows", "[Ung dung] Giong /apps"),
        ("software", "[Ung dung] Phan mem da cai tren may"),
        ("installed", "[Ung dung] Giong /software"),
    ]
    if config.ENABLE_OPEN_APPS:
        items.append(("open", "[Ung dung] Mo app, vi du /open chrome"))
    if config.ENABLE_SCREENSHOT:
        items.append(("screenshot", "[Chup] Chup man hinh"))
    if config.ENABLE_LOCK:
        items.append(("lock", "[Ung dung] Khoa man hinh"))
    if config.ENABLE_CLOSE_APPS:
        items.append(("close", "[Ung dung] Tat 1 app, vi du /close chrome"))
        items.append(("close_apps", "[Ung dung] Tat het ung dung dang mo"))
    if config.ENABLE_VPN:
        items.append(("vpn", "[VPN] Danh sach / bat tat Pritunl"))
        items.append(("vpn_on", "[VPN] Bat tat ca profile"))
        items.append(("vpn_off", "[VPN] Tat tat ca profile"))
    if config.ENABLE_SHUTDOWN_RESTART:
        items.append(("shutdown_now", "[Power] Tat may (can xac nhan)"))
        items.append(("restart_now", "[Power] Khoi dong lai (can xac nhan)"))
        items.append(("confirm_shutdown", "[Power] Xac nhan tat may"))
        items.append(("confirm_restart", "[Power] Xac nhan khoi dong lai"))
    if config.ENABLE_NOTE:
        items.append(("note", "[Ghi chu] Luu ghi chu vao may"))
    if config.ENABLE_AUTOSTART:
        items.append(("autostart", "[Service] Dang ky chay khi khoi dong"))
        items.append(("autostart_off", "[Service] Go bo service khoi dong"))
    items.append(("service", "[Service] Trang thai service khoi dong"))
    items.append(("reload", "[Service] Khoi dong lai listen"))
    if config.ENABLE_AUTO_UPDATE:
        items.append(("update", "[Cap nhat] Git pull va restart listen"))
    items.append(("help", "[Menu] Danh sach toan bo lenh"))
    return [{"command": name, "description": desc} for name, desc in items]


# ------------------------------- Xu ly tung lenh ------------------------------

def _cmd_status(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    try:
        telegram_api.send_message(chat_id, build_status_text())
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /status: {e}", parse_mode="")


def _cmd_help(chat_id: str, args: str) -> None:
    try:
        telegram_api.send_message(chat_id, build_help_text())
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /help: {e}", parse_mode="")


def _cmd_cpu(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    try:
        telegram_api.send_message(chat_id, system_info.get_cpu_text())
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /cpu: {e}", parse_mode="")


def _cmd_ram(chat_id: str, args: str) -> None:
    try:
        telegram_api.send_message(chat_id, system_info.get_ram_text())
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /ram: {e}", parse_mode="")


def _cmd_disk(chat_id: str, args: str) -> None:
    try:
        telegram_api.send_message(chat_id, system_info.get_disk_text())
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /disk: {e}", parse_mode="")


def _cmd_procs(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    try:
        telegram_api.send_message(chat_id, system_info.get_top_processes_text())
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /procs: {e}", parse_mode="")


def _cmd_apps(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    try:
        telegram_api.send_message(chat_id, system_info.get_running_apps_text())
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /apps: {e}", parse_mode="")


def _cmd_software(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    try:
        pages = system_info.get_installed_software_chunks(args)
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /software: {e}", parse_mode="")
        return
    max_pages = 4
    for page in pages[:max_pages]:
        telegram_api.send_message(chat_id, page)
    extra = len(pages) - max_pages
    if extra > 0:
        telegram_api.reply(
            chat_id,
            f"Con {extra} trang. Loc cho ngan hon, vi du /software chrome",
            parse_mode="",
        )
    if config.ENABLE_OPEN_APPS and args.strip():
        launchable = system_info.get_launchable_apps(args)
        keyboard = system_info.open_app_keyboard(launchable)
        if keyboard:
            telegram_api.reply(
                chat_id,
                "Bam nut de mo app:",
                parse_mode="",
                reply_markup=keyboard,
            )


def _cmd_open(chat_id: str, args: str) -> None:
    if not config.ENABLE_OPEN_APPS:
        telegram_api.send_message(chat_id, "Tinh nang mo app dang bi tat (ENABLE_OPEN_APPS=false trong .env).")
        return
    query = args.strip()
    if not query:
        telegram_api.reply(
            chat_id,
            "Gui /open tenapp. Vi du /open chrome\nHoac /software chrome roi bam Mo.",
            parse_mode="",
        )
        return
    status, item, hits = system_info.match_launchable(query)
    if status == "none":
        telegram_api.reply(
            chat_id,
            f"Khong khop app nao voi '{query}'. Thu /software {query} hoac /open chrome",
            parse_mode="",
        )
        return
    if status == "many":
        keyboard = system_info.open_app_keyboard(hits)
        names = ", ".join(x["name"] for x in hits[:8])
        telegram_api.reply(
            chat_id,
            f"Nhieu app khop: {names}\nBam nut hoac ghi ro hon.",
            parse_mode="",
            reply_markup=keyboard,
        )
        return
    ok, msg = system_info.launch_app(item or {})
    telegram_api.reply(chat_id, ("OK. " if ok else "Loi. ") + msg, parse_mode="")


def _cmd_ip(chat_id: str, args: str) -> None:
    try:
        local_ip = system_info.get_local_ip()
        public_ip = system_info.get_public_ip()
        telegram_api.send_message(
            chat_id,
            f"🌐 <b>DIA CHI IP</b>\nNoi bo (LAN): {local_ip}\nCong khai: {public_ip}",
        )
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /ip: {e}", parse_mode="")


def _cmd_screenshot(chat_id: str, args: str) -> None:
    if not config.ENABLE_SCREENSHOT:
        telegram_api.send_message(chat_id, "Tinh nang screenshot dang bi tat (ENABLE_SCREENSHOT=false trong .env).")
        return
    telegram_api.send_chat_action(chat_id, "upload_photo")
    path = ""
    try:
        ok, result = actions.take_screenshot()
        if ok:
            path = result
            sent, err = telegram_api.send_photo(chat_id, result, caption="Man hinh hien tai")
            if not sent:
                telegram_api.reply(
                    chat_id,
                    f"Da chup anh nhung khong gui duoc len Telegram. {err}. Listen van dang chay.",
                    parse_mode="",
                )
        else:
            telegram_api.reply(chat_id, f"Loi. {result}", parse_mode="")
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /screenshot: {e}", parse_mode="")
    finally:
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass


def _cmd_lock(chat_id: str, args: str) -> None:
    if not config.ENABLE_LOCK:
        telegram_api.send_message(chat_id, "Tinh nang khoa man hinh dang bi tat (ENABLE_LOCK=false trong .env).")
        return
    try:
        ok, msg = actions.lock_screen()
        telegram_api.reply(chat_id, ("OK. " if ok else "Loi. ") + msg, parse_mode="")
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /lock: {e}", parse_mode="")


def _cmd_close_apps(chat_id: str, args: str) -> None:
    if not config.ENABLE_CLOSE_APPS:
        telegram_api.send_message(chat_id, "Tinh nang tat app dang bi tat (ENABLE_CLOSE_APPS=false trong .env).")
        return
    if args.strip():
        _cmd_close(chat_id, args)
        return
    try:
        apps = system_info.get_running_apps()
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /close_apps khi liet ke app: {e}", parse_mode="")
        return
    names = [str(a.get("name") or "") for a in apps if a.get("name")]
    preview_raw = ", ".join(names[:12]) if names else "(khong liet ke duoc)"
    preview = preview_raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    extra = f" va {len(names) - 12} app khac" if len(names) > 12 else ""
    _request_confirmation(
        chat_id, "close_apps",
        "⚠️ Ban co chac muon <b>TAT HET UNG DUNG DANG MO</b>?\n"
        "Giu lai desktop, listener, va cua so dang chay bot.\n"
        f"Dang mo ({len(names)}): {preview}{extra}\n"
        f"Tat 1 app: /close chrome\n"
        f"Nhan nut ben duoi, hoac gui /confirm_close_apps trong {CONFIRM_TIMEOUT_SECONDS} giay.",
        "confirm_close_apps",
        "Xac nhan TAT HET",
    )


def _cmd_close(chat_id: str, args: str) -> None:
    if not config.ENABLE_CLOSE_APPS:
        telegram_api.send_message(chat_id, "Tinh nang tat app dang bi tat (ENABLE_CLOSE_APPS=false trong .env).")
        return
    query = args.strip()
    if not query:
        apps = system_info.get_running_apps()
        keyboard = system_info.close_running_keyboard(apps)
        telegram_api.reply(
            chat_id,
            "Gui /close tenapp (vi du /close chrome) hoac bam nut. Tat het: /close_apps",
            parse_mode="",
            reply_markup=keyboard,
        )
        return
    ok, msg, hits = actions.close_one_app(query)
    keyboard = system_info.close_running_keyboard(hits) if hits else None
    telegram_api.reply(chat_id, ("OK. " if ok else "Loi. ") + msg, parse_mode="", reply_markup=keyboard)


def _cmd_note(chat_id: str, args: str) -> None:
    if not config.ENABLE_NOTE:
        telegram_api.send_message(chat_id, "Tinh nang ghi chu dang bi tat (ENABLE_NOTE=false trong .env).")
        return
    if not args.strip():
        telegram_api.send_message(chat_id, "Dung: /note noi dung ghi chu")
        return
    try:
        ok, msg = actions.append_note(args.strip())
        telegram_api.reply(chat_id, ("OK. " if ok else "Loi. ") + msg, parse_mode="")
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /note: {e}", parse_mode="")


def _cmd_autostart(chat_id: str, args: str) -> None:
    if not config.ENABLE_AUTOSTART:
        telegram_api.send_message(chat_id, "Tinh nang dang ky service dang bi tat (ENABLE_AUTOSTART=false trong .env).")
        return
    arg = args.strip().lower()
    if arg in ("off", "stop", "disable", "uninstall"):
        _cmd_autostart_off(chat_id, "")
        return
    if arg in ("status", "info"):
        _cmd_service(chat_id, "")
        return
    if arg in ("reload", "restart", "refresh"):
        _cmd_reload(chat_id, "")
        return
    force = arg in ("force", "reinstall", "again")

    def _run() -> None:
        if not force:
            try:
                already, detail = autostart.is_registered()
            except Exception:
                already, detail = False, ""
            if already or autostart.running_as_listener():
                telegram_api.send_message(
                    chat_id,
                    "✅ Autostart <b>dang dung</b> — may vua boot, listen da tu chay.\n"
                    "Khong can tim listen cu (chi can 1 process).\n"
                    f"{detail or 'Listen hien tai dang tra loi Telegram.'}\n"
                    "Xem chi tiet: /service\n"
                    "Muon cai lai: /autostart force",
                )
                return
        if platform.system() == "Windows":
            telegram_api.send_message(
                chat_id,
                "Dang mo hop thoai Administrator (UAC) tren may Windows.\n"
                "Hay bam <b>Yes</b> tren man hinh may (khong bam duoc tu Telegram).\n"
                "Hoac tren may chay: <code>python main.py install</code>.",
            )
        ok, msg = autostart.install(start_listener_now=False)
        prefix = (
            "Chi dang ky lich khoi dong, <b>giu listen hien tai</b> "
            "(khong mo process thu 2 — tranh loi getUpdates Conflict).\n"
        )
        telegram_api.send_message(
            chat_id,
            ("✅ " if ok else "❌ ") + prefix + msg.replace("&", "&amp;").replace("<", "&lt;"),
        )

    _run()


def _cmd_autostart_off(chat_id: str, args: str) -> None:
    if not config.ENABLE_AUTOSTART:
        telegram_api.send_message(chat_id, "Tinh nang dang ky service dang bi tat (ENABLE_AUTOSTART=false trong .env).")
        return
    if platform.system() == "Windows":
        telegram_api.send_message(
            chat_id,
            "Dang mo hop thoai Administrator (UAC) tren may Windows.\n"
            "Hay bam <b>Yes</b> de go Task Scheduler.",
        )
    try:
        ok, msg = autostart.uninstall()
        telegram_api.reply(chat_id, ("OK. " if ok else "Loi. ") + msg, parse_mode="")
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /autostart_off: {e}", parse_mode="")


def _cmd_reload(chat_id: str, args: str) -> None:
    telegram_api.log(f"Nhan /reload tu {chat_id}")

    def _run() -> None:
        telegram_api.reply(
            chat_id,
            "Listen cu se thoat, listen moi se bao khi san sang.",
            parse_mode="",
        )
        updater.spawn_new_listener(kind="reload")

    _run()


def _cmd_service(chat_id: str, args: str) -> None:
    arg = args.strip().lower()
    if arg in ("reload", "restart", "refresh"):
        _cmd_reload(chat_id, "")
        return
    telegram_api.log(f"Nhan /service tu {chat_id}")

    def _run() -> None:
        text = autostart.status_text(fast=True)
        plain = (
            text.replace("<b>", "")
            .replace("</b>", "")
            .replace("<code>", "")
            .replace("</code>", "")
        )
        sent = telegram_api.reply(chat_id, plain, parse_mode="")
        if not sent:
            telegram_api.reply(
                chat_id,
                "SERVICE: listen dang tra loi. Autostart: xem file Startup "
                "(PC Monitor - Lang nghe Telegram.vbs).",
                parse_mode="",
            )

    _run()


def _cmd_update(chat_id: str, args: str) -> None:
    telegram_api.log(f"Nhan /update tu {chat_id}")

    def _run() -> None:
        try:
            ok, msg, will_restart = updater.apply_and_restart()
        except Exception as e:
            telegram_api.log(f"/update loi: {e}")
            ok, msg, will_restart = False, f"Loi /update: {e}", False
        telegram_api.send_message(
            chat_id,
            ("OK. " if ok else "Loi. ") + str(msg)[:3500],
            parse_mode="",
        )
        if ok and will_restart:
            time.sleep(0.5)
            updater.spawn_new_listener()

    _run()


def _power_lock_line() -> str:
    try:
        locked = system_info.is_screen_locked()
    except Exception:
        locked = None
    if locked is True:
        return "Man hinh: <b>dang khoa</b> — van tat/restart duoc (force, khong cho app hoi)."
    if locked is False:
        return "Man hinh: dang mo."
    return "Man hinh: khong xac dinh."


def _request_confirmation(chat_id: str, action: str, prompt: str, confirm_data: str, confirm_label: str) -> None:
    _pending_confirmations[chat_id] = {
        "action": action,
        "expires_at": time.time() + CONFIRM_TIMEOUT_SECONDS,
    }
    markup = {
        "inline_keyboard": [[
            {"text": confirm_label, "callback_data": confirm_data},
            {"text": "Huy", "callback_data": "cancel_power"},
        ]]
    }
    sent = telegram_api.send_message(chat_id, prompt, reply_markup=markup)
    if not sent:
        confirm_cmd = {
            "shutdown": "/confirm_shutdown",
            "restart": "/confirm_restart",
            "close_apps": "/confirm_close_apps",
        }.get(action, "/help")
        telegram_api.send_message(
            chat_id,
            f"Can xac nhan. Gui {confirm_cmd} trong {CONFIRM_TIMEOUT_SECONDS} giay.",
            parse_mode="",
        )


def _cmd_shutdown_now(chat_id: str, args: str) -> None:
    if not config.ENABLE_SHUTDOWN_RESTART:
        telegram_api.send_message(chat_id, "Tinh nang tat/khoi dong lai dang bi tat (ENABLE_SHUTDOWN_RESTART=false trong .env).")
        return
    _request_confirmation(
        chat_id, "shutdown",
        "⚠️ Ban co chac muon <b>TAT MAY NGAY BAY GIO</b>?\n"
        f"{_power_lock_line()}\n"
        f"Nhan nut ben duoi, hoac gui /confirm_shutdown trong {CONFIRM_TIMEOUT_SECONDS} giay.",
        "confirm_shutdown",
        "Xac nhan TAT MAY",
    )


def _cmd_restart_now(chat_id: str, args: str) -> None:
    if not config.ENABLE_SHUTDOWN_RESTART:
        telegram_api.send_message(chat_id, "Tinh nang tat/khoi dong lai dang bi tat (ENABLE_SHUTDOWN_RESTART=false trong .env).")
        return
    telegram_api.log(f"Nhan /restart_now tu {chat_id} args={args!r}")
    arg = args.strip().lower()
    pending = _pending_confirmations.get(chat_id)
    if arg in ("yes", "now", "ok", "confirm") or (
        pending and pending["action"] == "restart" and time.time() <= pending["expires_at"]
    ):
        telegram_api.send_message(chat_id, "Dang gui lenh restart...")
        _confirm(chat_id, "restart", actions.restart_now) if pending else _run_restart(chat_id)
        return
    telegram_api.send_message(chat_id, "Da nhan /restart_now — can xac nhan ben duoi.")
    _request_confirmation(
        chat_id, "restart",
        "⚠️ Ban co chac muon <b>KHOI DONG LAI MAY NGAY BAY GIO</b>?\n"
        f"{_power_lock_line()}\n"
        f"Nhan nut, gui /confirm_restart, hoac gui lai /restart_now trong {CONFIRM_TIMEOUT_SECONDS} giay.",
        "confirm_restart",
        "Xac nhan RESTART",
    )


def _run_restart(chat_id: str) -> None:
    _pending_confirmations.pop(chat_id, None)
    try:
        ok, msg = actions.restart_now()
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi restart: {e}", parse_mode="")
        return
    telegram_api.reply(chat_id, ("OK. " if ok else "Loi. ") + msg, parse_mode="")


def _confirm(chat_id: str, expected_action: str, execute_fn) -> None:
    pending = _pending_confirmations.get(chat_id)
    expired = bool(pending and time.time() > pending["expires_at"])
    mismatch = not pending or pending["action"] != expected_action
    if mismatch and expected_action != "close_apps":
        telegram_api.send_message(chat_id, "Khong co lenh nao dang cho xac nhan. Hay gui lai lenh goc truoc.")
        return
    if expired and expected_action != "close_apps":
        telegram_api.send_message(chat_id, "Da het thoi gian xac nhan. Hay gui lai lenh goc neu van muon thuc hien.")
        _pending_confirmations.pop(chat_id, None)
        return
    if pending and (expired or pending["action"] == expected_action):
        _pending_confirmations.pop(chat_id, None)
    if mismatch and expected_action == "close_apps":
        telegram_api.log("close_apps xac nhan khong qua pending — van tat app")

    try:
        ok, msg = execute_fn()
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi khi thuc hien {expected_action}: {e}", parse_mode="")
        return
    telegram_api.reply(chat_id, ("OK. " if ok else "Loi. ") + str(msg), parse_mode="")


def _cmd_confirm_shutdown(chat_id: str, args: str) -> None:
    _confirm(chat_id, "shutdown", actions.shutdown_now)


def _cmd_confirm_restart(chat_id: str, args: str) -> None:
    pending = _pending_confirmations.get(chat_id)
    if not pending or pending["action"] != "restart":
        telegram_api.send_message(chat_id, "Dang restart (khong can gui /restart_now lai)...")
        _run_restart(chat_id)
        return
    _confirm(chat_id, "restart", actions.restart_now)


def _cmd_confirm_close_apps(chat_id: str, args: str) -> None:
    if not config.ENABLE_CLOSE_APPS:
        telegram_api.send_message(chat_id, "Tinh nang tat app dang bi tat (ENABLE_CLOSE_APPS=false trong .env).")
        return
    telegram_api.send_chat_action(chat_id)
    _confirm(chat_id, "close_apps", actions.close_all_apps)


def _vpn_guard(chat_id: str) -> bool:
    if not config.ENABLE_VPN:
        telegram_api.send_message(chat_id, "Tinh nang VPN dang bi tat (ENABLE_VPN=false trong .env).")
        return False
    return True


def _cmd_vpn(chat_id: str, args: str) -> None:
    if not _vpn_guard(chat_id):
        return
    arg = args.strip().lower()
    if arg in ("on", "start", "up"):
        _cmd_vpn_on(chat_id, "")
        return
    if arg in ("off", "stop", "down"):
        _cmd_vpn_off(chat_id, "")
        return

    def _run() -> None:
        ok, err, profiles = vpn.list_profiles()
        if not ok:
            telegram_api.send_message(chat_id, "VPN: " + err, parse_mode="")
            return
        sent = telegram_api.send_message(
            chat_id,
            vpn.format_list_text(profiles),
            reply_markup=vpn.list_keyboard(profiles),
        )
        if not sent:
            telegram_api.send_message(chat_id, vpn.format_list_text(profiles), parse_mode="")

    _run()


def _cmd_vpn_on(chat_id: str, args: str) -> None:
    if not _vpn_guard(chat_id):
        return
    query = args.strip()

    def _run() -> None:
        if not query or query.lower() in ("all", "tatca", "*"):
            ok, msg = vpn.start_all()
            telegram_api.reply(
                chat_id,
                ("OK. " if ok else "Loi. ") + msg,
                parse_mode="",
            )
            return
        ok, err, profiles = vpn.list_profiles()
        if not ok:
            telegram_api.reply(chat_id, "Loi. " + err, parse_mode="")
            return
        profile = vpn.match_profile(query, profiles)
        if not profile:
            telegram_api.reply(chat_id, "Khong khop profile nao. Gui /vpn de xem danh sach.", parse_mode="")
            return
        started, msg = vpn.start_profile(profile["id"])
        telegram_api.reply(chat_id, ("OK. " if started else "Loi. ") + msg, parse_mode="")

    _run()


def _cmd_vpn_off(chat_id: str, args: str) -> None:
    if not _vpn_guard(chat_id):
        return
    query = args.strip()

    def _run() -> None:
        if not query or query.lower() in ("all", "tatca", "*"):
            ok, msg = vpn.stop_all()
            telegram_api.reply(chat_id, ("OK. " if ok else "Loi. ") + msg, parse_mode="")
            return
        ok, err, profiles = vpn.list_profiles()
        if not ok:
            telegram_api.reply(chat_id, "Loi. " + err, parse_mode="")
            return
        profile = vpn.match_profile(query, profiles)
        if not profile:
            telegram_api.reply(chat_id, "Khong khop profile nao. Gui /vpn de xem danh sach.", parse_mode="")
            return
        stopped, msg = vpn.stop_profile(profile["id"])
        telegram_api.reply(chat_id, ("OK. " if stopped else "Loi. ") + msg, parse_mode="")

    _run()


def handle_callback(chat_id: str, data: str) -> bool:
    """Xu ly nut bam inline. Tra ve True neu la callback cua bot."""
    try:
        if data == "confirm_shutdown":
            _cmd_confirm_shutdown(chat_id, "")
            return True
        if data == "confirm_restart":
            _cmd_confirm_restart(chat_id, "")
            return True
        if data == "confirm_close_apps":
            _cmd_confirm_close_apps(chat_id, "")
            return True
        if data == "cancel_power":
            _pending_confirmations.pop(chat_id, None)
            telegram_api.reply(chat_id, "Da huy lenh.", parse_mode="")
            return True
        if data == "vpn_on_all":
            _cmd_vpn_on(chat_id, "all")
            return True
        if data == "vpn_off_all":
            _cmd_vpn_off(chat_id, "all")
            return True
        if data.startswith("vpn_on:"):
            _cmd_vpn_on(chat_id, data.split(":", 1)[1])
            return True
        if data.startswith("vpn_off:"):
            _cmd_vpn_off(chat_id, data.split(":", 1)[1])
            return True
        if data.startswith("o:"):
            _cmd_open(chat_id, data.split(":", 1)[1])
            return True
        if data.startswith("c:"):
            _cmd_close(chat_id, data.split(":", 1)[1])
            return True
        telegram_api.reply(chat_id, f"Khong hieu nut bam: {data}", parse_mode="")
        return True
    except Exception as e:
        telegram_api.log(f"Loi callback {data}: {e}")
        telegram_api.reply(chat_id, f"Loi nut bam: {e}\nListen van dang chay.", parse_mode="")
        return True


# ------------------------------- Bang dieu phoi -------------------------------

COMMAND_TABLE = {
    "/status": _cmd_status,
    "/ping": _cmd_status,
    "/help": _cmd_help,
    "/start": _cmd_help,
    "/cpu": _cmd_cpu,
    "/ram": _cmd_ram,
    "/disk": _cmd_disk,
    "/procs": _cmd_procs,
    "/apps": _cmd_apps,
    "/windows": _cmd_apps,
    "/software": _cmd_software,
    "/installed": _cmd_software,
    "/programs": _cmd_software,
    "/open": _cmd_open,
    "/run": _cmd_open,
    "/ip": _cmd_ip,
    "/screenshot": _cmd_screenshot,
    "/lock": _cmd_lock,
    "/close": _cmd_close,
    "/close_apps": _cmd_close_apps,
    "/confirm_close_apps": _cmd_confirm_close_apps,
    "/vpn": _cmd_vpn,
    "/vpn_list": _cmd_vpn,
    "/vpn_on": _cmd_vpn_on,
    "/vpn_off": _cmd_vpn_off,
    "/note": _cmd_note,
    "/autostart": _cmd_autostart,
    "/autostart_off": _cmd_autostart_off,
    "/service": _cmd_service,
    "/svc": _cmd_service,
    "/reload": _cmd_reload,
    "/service_reload": _cmd_reload,
    "/update": _cmd_update,
    "/shutdown_now": _cmd_shutdown_now,
    "/restart_now": _cmd_restart_now,
    "/confirm_shutdown": _cmd_confirm_shutdown,
    "/confirm_restart": _cmd_confirm_restart,
}


def dispatch(chat_id: str, text: str) -> bool:
    """Tra ve True neu tim thay lenh tuong ung va da xu ly."""
    text = text.strip()
    if not text.startswith("/"):
        return False

    parts = text.split(maxsplit=1)
    command = parts[0].split("@")[0].lower().replace("-", "_")
    args = parts[1] if len(parts) > 1 else ""

    handler = COMMAND_TABLE.get(command)
    if handler is None:
        return False

    try:
        handler(chat_id, args)
    except Exception as e:
        telegram_api.log(f"Loi {command}: {e}")
        telegram_api.reply(
            chat_id,
            f"Loi {command}: {e}\nListen van dang chay. Xem pc_monitor.log neu can.",
            parse_mode="",
        )
    return True
