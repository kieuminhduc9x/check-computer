"""
telegram_api.py - Lop giao tiep voi Telegram Bot API.
Dung thu vien `requests` cho don gian va de xu ly upload anh (multipart).
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from . import config

API_BASE = "https://api.telegram.org/bot{token}/{method}"
_HTML_TAG = re.compile(r"<[^>]+>")
_log_lock = threading.Lock()
_tls = threading.local()
_poll_session = requests.Session()
_poll_session.mount("https://", HTTPAdapter(pool_connections=2, pool_maxsize=2, max_retries=0))


def _thread_session() -> requests.Session:
    """Moi thread 1 Session — requests.Session khong thread-safe."""
    sess = getattr(_tls, "session", None)
    if sess is None:
        sess = requests.Session()
        sess.mount("https://", HTTPAdapter(pool_connections=2, pool_maxsize=4, max_retries=0))
        _tls.session = sess
    return sess


def log(message: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    with _log_lock:
        print(line, flush=True)
        try:
            with open(config.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def _url(method: str) -> str:
    return API_BASE.format(token=config.BOT_TOKEN, method=method)


def _send_http(method: str, url: str, timeout: float, **kwargs):
    """HTTP cho sendMessage/sendPhoto: retry 429, khong dung chung ket noi voi getUpdates."""
    last_resp = None
    last_err = None
    for attempt in range(4):
        try:
            last_resp = _thread_session().request(method, url, timeout=timeout, **kwargs)
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (attempt + 1))
            continue
        if last_resp.status_code != 429:
            return last_resp
        raw = last_resp.headers.get("Retry-After", "1")
        try:
            wait_s = min(float(raw), 8.0)
        except ValueError:
            wait_s = 1.0
        time.sleep(max(0.4, wait_s))
    if last_resp is not None:
        return last_resp
    raise last_err or RuntimeError("Telegram HTTP that bai")


def send_chat_action(chat_id: str, action: str = "typing") -> None:
    try:
        _thread_session().post(
            _url("sendChatAction"),
            data={"chat_id": chat_id, "action": action},
            timeout=2,
        )
    except Exception:
        pass


def _strip_html(text: str) -> str:
    return _HTML_TAG.sub("", str(text))


def _post_message(
    chat_id: str,
    text: str,
    parse_mode: str = "",
    reply_markup: dict | None = None,
    timeout: int = 15,
) -> bool:
    data = {"chat_id": chat_id, "text": str(text)[:4000] or "(trong)"}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    resp = _send_http("POST", _url("sendMessage"), timeout=timeout, data=data)
    try:
        result = resp.json()
    except Exception:
        result = {}
    return bool(result.get("ok"))


def send_message(
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
    timeout: int = 15,
) -> bool:
    """Gui tin. Khong raise — that bai thi thu text thuong, roi tra False."""
    if not text:
        text = "(trong)"
    text = str(text)[:4000]
    try:
        if _post_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, timeout=timeout):
            return True
        log("Telegram loi sendMessage, thu gui text thuong.")
        if _post_message(chat_id, _strip_html(text), parse_mode="", timeout=min(timeout, 8)):
            return True
        log("Telegram van loi khi gui tin nhan.")
        return False
    except Exception as e:
        log(f"Loi khi gui tin nhan: {e}")
        try:
            return _post_message(chat_id, _strip_html(text)[:500], parse_mode="", timeout=5)
        except Exception as e2:
            log(f"Gui tin nhan that bai lan cuoi: {e2}")
            return False


def reply(
    chat_id: str,
    text: str,
    parse_mode: str = "",
    reply_markup: dict | None = None,
    timeout: int = 15,
) -> bool:
    """Ket qua lenh: luon co gang gui, khong raise, mac dinh text thuong."""
    try:
        return send_message(
            chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, timeout=timeout
        )
    except Exception as e:
        log(f"reply that bai: {e}")
        return False


def send_to_all(text: str, parse_mode: str = "HTML") -> bool:
    if not config.ALLOWED_CHAT_IDS:
        return False
    ok_all = True
    for chat_id in config.ALLOWED_CHAT_IDS:
        ok_all = send_message(chat_id, text, parse_mode=parse_mode) and ok_all
    return ok_all


def send_to_all_retry(text: str, attempts: int = 12, delay_sec: float = 10) -> bool:
    """Gui lai khi may moi boot, mang/Telegram chua san sang."""
    for i in range(1, attempts + 1):
        if send_to_all(text):
            if i > 1:
                log(f"Gui thong bao thanh cong o lan thu {i}.")
            return True
        log(f"Chua gui duoc thong bao (lan {i}/{attempts}), thu lai sau {delay_sec}s")
        time.sleep(delay_sec)
    return False


def boot_notify_recently_sent(window_sec: int = 120) -> bool:
    if not config.READY_STAMP_FILE.exists():
        return False
    try:
        ts = float(config.READY_STAMP_FILE.read_text(encoding="utf-8").strip())
        return (time.time() - ts) < window_sec
    except Exception:
        return False


def mark_boot_notified() -> None:
    try:
        config.READY_STAMP_FILE.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def clear_webhook() -> None:
    """Tranh getUpdates bi chan neu bot tung bat webhook."""
    try:
        _send_http(
            "POST",
            _url("deleteWebhook"),
            timeout=10,
            data={"drop_pending_updates": "false"},
        )
    except Exception:
        pass


def set_my_commands(commands: list) -> bool:
    """Dang ky danh sach lenh len menu '/' cua Telegram."""
    try:
        resp = _send_http(
            "POST",
            _url("setMyCommands"),
            timeout=15,
            json={"commands": commands},
        )
        result = resp.json()
        if result.get("ok"):
            log(f"Da cap nhat menu Telegram ({len(commands)} lenh).")
            return True
        log(f"Khong cap nhat duoc menu Telegram: {result}")
        return False
    except Exception as e:
        log(f"Loi mang khi cap nhat menu Telegram: {e}")
        return False


def send_photo(chat_id: str, image_path: Path, caption: str = "") -> tuple[bool, str]:
    """Gui anh. Tra ve (ok, thong_bao_loi). Mo lai file moi lan retry."""
    image_path = Path(image_path)
    last_err = "khong gui duoc anh"
    for attempt in range(2):
        try:
            with open(image_path, "rb") as f:
                resp = _thread_session().post(
                    _url("sendPhoto"),
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=20,
                )
            try:
                result = resp.json()
            except Exception:
                result = {}
            if result.get("ok"):
                return True, ""
            if resp.status_code == 429:
                raw = resp.headers.get("Retry-After", "1")
                try:
                    wait_s = min(float(raw), 8.0)
                except ValueError:
                    wait_s = 1.0
                time.sleep(wait_s)
                last_err = "Telegram 429 (qua nhieu request)"
                continue
            desc = result.get("description") or str(result)[:180]
            last_err = f"HTTP {resp.status_code}: {desc}"
            log(f"Telegram tra ve loi khi gui anh (lan {attempt + 1}): {result}")
        except Exception as e:
            last_err = str(e)
            log(f"Loi khi gui anh (lan {attempt + 1}): {e}")
        time.sleep(0.5 * (attempt + 1))
    return False, last_err


def api_reachable(timeout: float = 5) -> bool:
    """Kiem tra api.telegram.org con ra duoc khong (sau khi bat VPN)."""
    try:
        resp = _send_http("GET", _url("getMe"), timeout=timeout)
        data = resp.json()
        return bool(data.get("ok"))
    except Exception:
        return False


def get_updates(offset: int, timeout: int) -> dict:
    try:
        resp = _poll_session.post(
            _url("getUpdates"),
            data={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": json.dumps(["message", "callback_query"]),
            },
            timeout=timeout + 10,
        )
        try:
            data = resp.json()
        except Exception:
            return {"ok": False, "description": f"Telegram JSON loi ({resp.status_code})"}
        if isinstance(data, dict):
            return data
        return {"ok": False, "description": str(data)[:300]}
    except Exception as e:
        return {"ok": False, "description": str(e)}


def answer_callback_query(callback_id: str, text: str = "") -> None:
    try:
        data = {"callback_query_id": callback_id}
        if text:
            data["text"] = str(text)[:180]
        _send_http("POST", _url("answerCallbackQuery"), timeout=2, data=data)
    except Exception:
        pass
