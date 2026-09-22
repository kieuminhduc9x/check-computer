"""
commands.py - Noi dung tin nhan va bang dieu phoi lenh Telegram.

Moi lenh la 1 ham nhan (chat_id) va tu gui phan hoi qua telegram_api.
Lenh nguy hiem (tat may / khoi dong lai) can xac nhan 2 buoc trong vong 30s.
"""

import time
import threading
from datetime import datetime
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
CONFIRM_TIMEOUT_SECONDS = 30


def _reply(chat_id: str, text: str, parse_mode: str = "HTML", reply_markup: dict | None = None) -> bool:
    return telegram_api.reply(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)


def _bg(chat_id: str, label: str, fn) -> None:
    """Chay lenh lau trong thread; loi van gui Telegram, khong crash listen."""

    def _run() -> None:
        try:
            fn()
        except Exception as e:
            telegram_api.log(f"{label}: {e}")
            telegram_api.reply(
                chat_id,
                f"Loi {label}: {e}\nListen van dang chay.",
                parse_mode="",
            )

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
        "🤖 <b>Danh sach lenh</b> (ban day du: co /service /autostart)",
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
        f"/close_apps — tat het ung dung dang mo, can xac nhan{_disabled_suffix(config.ENABLE_CLOSE_APPS)}",
        f"/vpn — danh sach profile Pritunl, nut bat/tat{_disabled_suffix(config.ENABLE_VPN)}",
        f"/vpn_on — bat tat ca profile chua ket noi{_disabled_suffix(config.ENABLE_VPN)}",
        f"/vpn_off — tat tat ca profile dang ket noi{_disabled_suffix(config.ENABLE_VPN)}",
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
        "/reload — khoi dong lai listen (nap code, khong git pull)",
        "/service reload — giong /reload",
        f"/update — git pull va restart listen{_disabled_suffix(config.ENABLE_AUTO_UPDATE)}",
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
    if config.ENABLE_CLOSE_APPS:
        items.append(("close_apps", "Tat het ung dung dang mo"))
    if config.ENABLE_VPN:
        items.append(("vpn", "Danh sach / bat tat Pritunl VPN"))
        items.append(("vpn_on", "Bat tat ca profile Pritunl"))
        items.append(("vpn_off", "Tat tat ca profile Pritunl"))
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
    items.append(("reload", "Khoi dong lai listen (nap code)"))
    if config.ENABLE_AUTO_UPDATE:
        items.append(("update", "Git pull va restart listen"))
    items.append(("help", "Danh sach toan bo lenh"))
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
    try:
        ok, result = actions.take_screenshot()
    except Exception as e:
        telegram_api.reply(chat_id, f"Loi /screenshot: {e}", parse_mode="")
        return
    if ok:
        sent = telegram_api.send_photo(chat_id, result, caption="Man hinh hien tai")
        if not sent:
            telegram_api.reply(
                chat_id,
                "Da chup anh nhung khong gui duoc len Telegram (file qua lon / mat mang). Xem pc_monitor.log tren may.",
                parse_mode="",
            )
    else:
        telegram_api.reply(chat_id, f"Loi. {result}", parse_mode="")


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
        f"Nhan nut ben duoi, hoac gui /confirm_close_apps trong {CONFIRM_TIMEOUT_SECONDS} giay.",
        "confirm_close_apps",
        "Xac nhan TAT APP",
    )


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
    telegram_api.send_message(chat_id, "Dang kiem tra /autostart...")
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

    _bg(chat_id, "/autostart", _run)


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
    telegram_api.send_message(
        chat_id,
        "Dang reload listen...\nListen cu se thoat, listen moi se bao khi san sang.",
        parse_mode="",
    )

    def _run() -> None:
        updater.spawn_new_listener(kind="reload")

    _bg(chat_id, "/reload", _run)


def _cmd_service(chat_id: str, args: str) -> None:
    arg = args.strip().lower()
    if arg in ("reload", "restart", "refresh"):
        _cmd_reload(chat_id, "")
        return
    telegram_api.log(f"Nhan /service tu {chat_id}")
    try:
        text = autostart.status_text(fast=True)
        plain = (
            text.replace("<b>", "")
            .replace("</b>", "")
            .replace("<code>", "")
            .replace("</code>", "")
        )
        sent = telegram_api.send_message(chat_id, plain, parse_mode="")
        if not sent:
            telegram_api.send_message(
                chat_id,
                "SERVICE: listen dang tra loi. Autostart: xem file Startup "
                "(PCMonitorPro_Listener.vbs). Chi tiet: python main.py service",
                parse_mode="",
            )
    except Exception as e:
        telegram_api.send_message(chat_id, f"Loi /service: {e}", parse_mode="")


def _cmd_update(chat_id: str, args: str) -> None:
    telegram_api.log(f"Nhan /update tu {chat_id}")
    telegram_api.send_chat_action(chat_id)
    sent = telegram_api.send_message(
        chat_id,
        "Dang git pull --ff-only...\nThuong tra loi trong 10-30 giay.",
        parse_mode="",
    )
    if not sent:
        telegram_api.log("Khong gui duoc tin ACK /update")

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

    _bg(chat_id, "/update", _run)


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
    if not pending or pending["action"] != expected_action:
        telegram_api.send_message(chat_id, "Khong co lenh nao dang cho xac nhan. Hay gui lai lenh goc truoc.")
        return
    if time.time() > pending["expires_at"]:
        telegram_api.send_message(chat_id, "Da het thoi gian xac nhan. Hay gui lai lenh goc neu van muon thuc hien.")
        del _pending_confirmations[chat_id]
        return

    del _pending_confirmations[chat_id]
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
    telegram_api.send_message(chat_id, "Dang doc profile Pritunl...", parse_mode="")

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

    _bg(chat_id, "/vpn", _run)


def _cmd_vpn_on(chat_id: str, args: str) -> None:
    if not _vpn_guard(chat_id):
        return
    telegram_api.send_chat_action(chat_id)
    telegram_api.reply(chat_id, "Dang bat VPN...", parse_mode="")
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

    _bg(chat_id, "/vpn_on", _run)


def _cmd_vpn_off(chat_id: str, args: str) -> None:
    if not _vpn_guard(chat_id):
        return
    telegram_api.send_chat_action(chat_id)
    telegram_api.reply(chat_id, "Dang tat VPN...", parse_mode="")
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

    _bg(chat_id, "/vpn_off", _run)


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
    "/ip": _cmd_ip,
    "/screenshot": _cmd_screenshot,
    "/lock": _cmd_lock,
    "/close_apps": _cmd_close_apps,
    "/closeall": _cmd_close_apps,
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
    command = parts[0].split("@")[0].lower()  # ho tro dang "/status@ten_bot"
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
