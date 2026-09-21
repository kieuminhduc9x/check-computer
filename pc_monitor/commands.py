"""
commands.py - Noi dung tin nhan va bang dieu phoi lenh Telegram.

Moi lenh la 1 ham nhan (chat_id) va tu gui phan hoi qua telegram_api.
Lenh nguy hiem (tat may / khoi dong lai) can xac nhan 2 buoc trong vong 30s.
"""

import time
from datetime import datetime

from . import config
from . import system_info
from . import actions
from . import telegram_api

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
        "shutdown": "🔴 MAY TINH SAP TAT / KHOI DONG LAI",
        "heartbeat": "💚 MAY TINH VAN DANG HOAT DONG",
    }
    title = titles.get(event, "ℹ️ THONG BAO TU MAY TINH")

    return (
        f"<b>{title}</b>\n"
        f"Ten may: {config.COMPUTER_NAME} ({host})\n"
        f"IP noi bo: {ip}\n"
        f"Thoi gian: {now_str}"
    )


def build_status_text() -> str:
    now_str = datetime.now().strftime("%H:%M:%S ngay %d/%m/%Y")
    host = system_info.get_hostname()
    ip = system_info.get_local_ip()
    uptime = system_info.get_uptime_str()
    return (
        f"🟢 <b>MAY TINH DANG BAT</b>\n"
        f"Ten may: {config.COMPUTER_NAME} ({host})\n"
        f"IP noi bo: {ip}\n"
        f"Da bat lien tuc: {uptime}\n"
        f"Thoi gian kiem tra: {now_str}"
    )


def build_help_text() -> str:
    lines = [
        "🤖 <b>Danh sach lenh ho tro:</b>",
        "",
        "<b>Trang thai</b>",
        "/status hoac /ping - May co dang bat khong, uptime bao lau",
        "/cpu - % su dung CPU",
        "/ram - % su dung RAM",
        "/disk - Dung luong cac o dia",
        "/procs - Top 5 tien trinh ngon CPU nhat",
        "/apps - Danh sach ung dung dang mo (co giao dien)",
        "/ip - IP noi bo va IP cong khai",
    ]
    if config.ENABLE_SCREENSHOT:
        lines.append("/screenshot - Chup man hinh hien tai")
    if config.ENABLE_LOCK:
        lines.append("/lock - Khoa man hinh may")
    if config.ENABLE_SHUTDOWN_RESTART:
        lines.append("/shutdown_now - Tat may (can xac nhan)")
        lines.append("/restart_now - Khoi dong lai may (can xac nhan)")
    if config.ENABLE_NOTE:
        lines.append("/note <noi dung> - Luu 1 ghi chu nhanh vao may")
    lines.append("/help - Xem lai danh sach nay")
    lines.append("")
    lines.append(
        "Luu y: neu may da tat, ban se KHONG nhan duoc phan hoi cho bat ky lenh "
        "nao ca — do la dau hieu may dang tat."
    )
    return "\n".join(lines)


# ------------------------------- Xu ly tung lenh ------------------------------

def _cmd_status(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, build_status_text())


def _cmd_help(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, build_help_text())


def _cmd_cpu(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, system_info.get_cpu_text())


def _cmd_ram(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, system_info.get_ram_text())


def _cmd_disk(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, system_info.get_disk_text())


def _cmd_procs(chat_id: str, args: str) -> None:
    telegram_api.send_message(chat_id, system_info.get_top_processes_text())


def _cmd_apps(chat_id: str, args: str) -> None:
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
    ok, result = actions.take_screenshot()
    if ok:
        telegram_api.send_photo(chat_id, result, caption="📸 Man hinh hien tai")
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
        telegram_api.send_message(chat_id, "Dung: /note <noi dung ghi chu>")
        return
    ok, msg = actions.append_note(args.strip())
    telegram_api.send_message(chat_id, ("✅ " if ok else "❌ ") + msg)


def _request_confirmation(chat_id: str, action: str, prompt: str) -> None:
    _pending_confirmations[chat_id] = {
        "action": action,
        "expires_at": time.time() + CONFIRM_TIMEOUT_SECONDS,
    }
    telegram_api.send_message(chat_id, prompt)


def _cmd_shutdown_now(chat_id: str, args: str) -> None:
    if not config.ENABLE_SHUTDOWN_RESTART:
        telegram_api.send_message(chat_id, "Tinh nang tat/khoi dong lai dang bi tat (ENABLE_SHUTDOWN_RESTART=false trong .env).")
        return
    _request_confirmation(
        chat_id, "shutdown",
        "⚠️ Ban co chac muon <b>TAT MAY NGAY BAY GIO</b>?\n"
        f"Gui /confirm_shutdown trong vong {CONFIRM_TIMEOUT_SECONDS} giay de xac nhan.",
    )


def _cmd_restart_now(chat_id: str, args: str) -> None:
    if not config.ENABLE_SHUTDOWN_RESTART:
        telegram_api.send_message(chat_id, "Tinh nang tat/khoi dong lai dang bi tat (ENABLE_SHUTDOWN_RESTART=false trong .env).")
        return
    _request_confirmation(
        chat_id, "restart",
        "⚠️ Ban co chac muon <b>KHOI DONG LAI MAY NGAY BAY GIO</b>?\n"
        f"Gui /confirm_restart trong vong {CONFIRM_TIMEOUT_SECONDS} giay de xac nhan.",
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
    "/ip": _cmd_ip,
    "/screenshot": _cmd_screenshot,
    "/lock": _cmd_lock,
    "/note": _cmd_note,
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
