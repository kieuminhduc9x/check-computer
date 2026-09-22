"""
commands.py - Noi dung tin nhan va bang dieu phoi lenh Telegram.

Moi lenh la 1 ham nhan (chat_id) va tu gui phan hoi qua telegram_api.
Lenh nguy hiem (tat may / khoi dong lai) can xac nhan 2 buoc trong vong 30s.
"""

import time
from datetime import datetime
import platform

from . import config
from . import system_info
from . import actions
from . import telegram_api
from . import autostart

# chat_id -> {"action": "shutdown"|"restart", "expires_at": float}
_pending_confirmations = {}
CONFIRM_TIMEOUT_SECONDS = 30


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
        extra += "\nListener Telegram dang chay — gui /status de kiem tra."

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
        "",
        "<b>Trang thai may</b>",
        "/status — may dang bat, CPU/RAM, app dang dung, app dang mo",
        "/ping — giong /status, dung de hoi may con online khong",
        "",
        "<b>Ung dung &amp; tai nguyen</b>",
        "/apps — danh sach ung dung / cua so dang mo",
        "/windows — giong /apps",
        "/cpu — % CPU",
        "/ram — % RAM",
        "/disk — dung luong o dia",
        "/procs — top 5 tien trinh ngon CPU",
        "/ip — IP noi bo va IP cong khai",
        "",
        "<b>Dieu khien</b>",
        f"/screenshot — chup man hinh{_disabled_suffix(config.ENABLE_SCREENSHOT)}",
        f"/lock — khoa man hinh{_disabled_suffix(config.ENABLE_LOCK)}",
        f"/shutdown_now — tat may, can xac nhan (ca khi khoa man hinh){_disabled_suffix(config.ENABLE_SHUTDOWN_RESTART)}",
        f"/restart_now — khoi dong lai, can xac nhan{_disabled_suffix(config.ENABLE_SHUTDOWN_RESTART)}",
        f"/confirm_shutdown — xac nhan tat may{_disabled_suffix(config.ENABLE_SHUTDOWN_RESTART)}",
        f"/confirm_restart — xac nhan khoi dong lai{_disabled_suffix(config.ENABLE_SHUTDOWN_RESTART)}",
        "",
        "<b>Khac</b>",
        f"/note noi dung — luu ghi chu vao may{_disabled_suffix(config.ENABLE_NOTE)}",
        f"/autostart — dang ky chay khi khoi dong may{_disabled_suffix(config.ENABLE_AUTOSTART)}",
        f"/autostart_off — go bo service khoi dong{_disabled_suffix(config.ENABLE_AUTOSTART)}",
        f"/service — xem service khoi dong da cai chua{_disabled_suffix(config.ENABLE_AUTOSTART)}",
        "/help — xem lai danh sach nay",
        "",
        "Neu may da tat, moi lenh se khong co phan hoi.",
    ]
    return "\n".join(lines)


def telegram_menu_commands() -> list:
    """Danh sach dang ky vao nut '/' tren Telegram (toi da 100 lenh)."""
    items = [
        ("status", "Trang thai may, CPU/RAM, app dang mo"),
        ("ping", "Kiem tra may con online"),
        ("apps", "Ung dung / cua so dang mo"),
        ("windows", "Giong /apps"),
        ("cpu", "Phan tram CPU"),
        ("ram", "Phan tram RAM"),
        ("disk", "Dung luong o dia"),
        ("procs", "Top tien trinh theo CPU"),
        ("ip", "IP noi bo va cong khai"),
    ]
    if config.ENABLE_SCREENSHOT:
        items.append(("screenshot", "Chup man hinh"))
    if config.ENABLE_LOCK:
        items.append(("lock", "Khoa man hinh"))
    if config.ENABLE_SHUTDOWN_RESTART:
        items.append(("shutdown_now", "Tat may (can xac nhan)"))
        items.append(("restart_now", "Khoi dong lai (can xac nhan)"))
        items.append(("confirm_shutdown", "Xac nhan tat may"))
        items.append(("confirm_restart", "Xac nhan khoi dong lai"))
    if config.ENABLE_NOTE:
        items.append(("note", "Luu ghi chu vao may"))
    if config.ENABLE_AUTOSTART:
        items.append(("autostart", "Dang ky chay khi khoi dong may"))
        items.append(("autostart_off", "Go bo service khoi dong"))
    items.append(("service", "Trang thai service khoi dong"))
    items.append(("help", "Danh sach toan bo lenh"))
    return [{"command": name, "description": desc} for name, desc in items]


# ------------------------------- Xu ly tung lenh ------------------------------

def _cmd_status(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    telegram_api.send_message(chat_id, build_status_text())


def _cmd_help(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, build_help_text())


def _cmd_cpu(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    telegram_api.send_message(chat_id, system_info.get_cpu_text())


def _cmd_ram(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, system_info.get_ram_text())


def _cmd_disk(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, system_info.get_disk_text())


def _cmd_procs(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    telegram_api.send_message(chat_id, system_info.get_top_processes_text())


def _cmd_apps(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    telegram_api.send_message(chat_id, system_info.get_running_apps_text())


def _cmd_ip(chat_id: str, args: str) -> None:
    local_ip = system_info.get_local_ip()
    public_ip = system_info.get_public_ip()
    telegram_api.send_message(
        chat_id,
        f"🌐 <b>DIA CHI IP</b>\nNoi bo (LAN): {local_ip}\nCong khai: {public_ip}",
    )


def _cmd_screenshot(chat_id: str, args: str) -> None:
    if not config.ENABLE_SCREENSHOT:
        telegram_api.send_message(chat_id, "Tinh nang screenshot dang bi tat (ENABLE_SCREENSHOT=false trong .env).")
        return
    telegram_api.send_chat_action(chat_id, "upload_photo")
    ok, result = actions.take_screenshot()
    if ok:
        sent = telegram_api.send_photo(chat_id, result, caption="Man hinh hien tai")
        if not sent:
            telegram_api.send_message(
                chat_id,
                "❌ Da chup anh nhung khong gui duoc len Telegram "
                "(file qua lon / mat mang). Xem pc_monitor.log tren may.",
            )
    else:
        telegram_api.send_message(chat_id, f"❌ {result}")


def _cmd_lock(chat_id: str, args: str) -> None:
    if not config.ENABLE_LOCK:
        telegram_api.send_message(chat_id, "Tinh nang khoa man hinh dang bi tat (ENABLE_LOCK=false trong .env).")
        return
    ok, msg = actions.lock_screen()
    telegram_api.send_message(chat_id, ("✅ " if ok else "❌ ") + msg)


def _cmd_note(chat_id: str, args: str) -> None:
    if not config.ENABLE_NOTE:
        telegram_api.send_message(chat_id, "Tinh nang ghi chu dang bi tat (ENABLE_NOTE=false trong .env).")
        return
    if not args.strip():
        telegram_api.send_message(chat_id, "Dung: /note noi dung ghi chu")
        return
    ok, msg = actions.append_note(args.strip())
    telegram_api.send_message(chat_id, ("✅ " if ok else "❌ ") + msg)


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
    telegram_api.send_chat_action(chat_id)
    if platform.system() == "Windows":
        telegram_api.send_message(
            chat_id,
            "Dang mo hop thoai Administrator (UAC) tren may Windows.\n"
            "Hay bam <b>Yes</b> de dang ky Task Scheduler bang lenh "
            "<code>python main.py install</code>.",
        )
    ok, msg = autostart.install(start_listener_now=False)
    prefix = (
        "Chi dang ky lich khoi dong, <b>giu listen hien tai</b> "
        "(khong mo process thu 2 — tranh loi getUpdates Conflict).\n"
    )
    telegram_api.send_message(chat_id, ("✅ " if ok else "❌ ") + prefix + msg.replace("&", "&amp;").replace("<", "&lt;"))


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
    ok, msg = autostart.uninstall()
    telegram_api.send_message(chat_id, ("✅ " if ok else "❌ ") + msg.replace("&", "&amp;").replace("<", "&lt;"))


def _cmd_service(chat_id: str, args: str) -> None:
    telegram_api.send_chat_action(chat_id)
    try:
        text = autostart.status_text()
    except Exception as e:
        safe = str(e).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        telegram_api.send_message(chat_id, f"❌ Khong doc duoc trang thai service.\n{safe}")
        return
    sent = telegram_api.send_message(chat_id, text)
    if not sent:
        telegram_api.send_message(
            chat_id,
            "Khong gui duoc chi tiet /service (tin qua dai hoac HTML loi). "
            "Tren may chay: python main.py service",
            parse_mode="",
        )


def _power_lock_line() -> str:
    locked = system_info.is_screen_locked()
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
    telegram_api.send_message(chat_id, prompt, reply_markup=markup)


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
    _request_confirmation(
        chat_id, "restart",
        "⚠️ Ban co chac muon <b>KHOI DONG LAI MAY NGAY BAY GIO</b>?\n"
        f"{_power_lock_line()}\n"
        f"Nhan nut ben duoi, hoac gui /confirm_restart trong {CONFIRM_TIMEOUT_SECONDS} giay.",
        "confirm_restart",
        "Xac nhan RESTART",
    )


def _confirm(chat_id: str, expected_action: str, execute_fn) -> None:
    pending = _pending_confirmations.get(chat_id)
    if not pending or pending["action"] != expected_action:
        telegram_api.send_message(chat_id, "Khong co lenh nao dang cho xac nhan. Hay gui lai lenh goc truoc.")
        return
    if time.time() > pending["expires_at"]:
        telegram_api.send_message(chat_id, "Da het thoi gian xac nhan. Hay gui lai lenh goc neu van muon thuc hien.")
        del _pending_confirmations[chat_id]
        return

    del _pending_confirmations[chat_id]
    ok, msg = execute_fn()
    telegram_api.send_message(chat_id, ("✅ " if ok else "❌ ") + msg)


def _cmd_confirm_shutdown(chat_id: str, args: str) -> None:
    _confirm(chat_id, "shutdown", actions.shutdown_now)


def _cmd_confirm_restart(chat_id: str, args: str) -> None:
    _confirm(chat_id, "restart", actions.restart_now)


def handle_callback(chat_id: str, data: str) -> bool:
    """Xu ly nut bam inline. Tra ve True neu la callback cua bot."""
    if data == "confirm_shutdown":
        _cmd_confirm_shutdown(chat_id, "")
        return True
    if data == "confirm_restart":
        _cmd_confirm_restart(chat_id, "")
        return True
    if data == "cancel_power":
        _pending_confirmations.pop(chat_id, None)
        telegram_api.send_message(chat_id, "Da huy lenh tat/khoi dong lai.")
        return True
    return False


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
    "/ip": _cmd_ip,
    "/screenshot": _cmd_screenshot,
    "/lock": _cmd_lock,
    "/note": _cmd_note,
    "/autostart": _cmd_autostart,
    "/autostart_off": _cmd_autostart_off,
    "/service": _cmd_service,
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
    command = parts[0].split("@")[0].lower()  # ho tro dang "/status@ten_bot"
    args = parts[1] if len(parts) > 1 else ""

    handler = COMMAND_TABLE.get(command)
    if handler is None:
        return False

    handler(chat_id, args)
    return True
