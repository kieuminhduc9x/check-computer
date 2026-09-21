"""
telegram_api.py - Lop giao tiep voi Telegram Bot API.
Dung thu vien `requests` cho don gian va de xu ly upload anh (multipart).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import requests

from . import config

API_BASE = "https://api.telegram.org/bot{token}/{method}"


def log(message: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    try:
        with open(config.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _url(method: str) -> str:
    return API_BASE.format(token=config.BOT_TOKEN, method=method)


def send_chat_action(chat_id: str, action: str = "typing") -> None:
    try:
        requests.post(
            _url("sendChatAction"),
            data={"chat_id": chat_id, "action": action},
            timeout=5,
        )
    except Exception:
        pass


def send_message(chat_id: str, text: str, parse_mode: str = "HTML", reply_markup: dict | None = None) -> bool:
    try:
        data = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        resp = requests.post(_url("sendMessage"), data=data, timeout=15)
        result = resp.json()
        if result.get("ok"):
            return True
        desc = str(result.get("description", "")).lower()
        if parse_mode and "parse" in desc:
            log(f"Tin nhan HTML bi loi, gui lai dang thuong: {result}")
            resp = requests.post(
                _url("sendMessage"),
                data={"chat_id": chat_id, "text": text},
                timeout=15,
            )
            result = resp.json()
            if result.get("ok"):
                return True
        log(f"Telegram tra ve loi khi gui tin nhan: {result}")
        return False
    except requests.RequestException as e:
        log(f"Loi mang khi gui tin nhan: {e}")
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


def set_my_commands(commands: list) -> bool:
    """Dang ky danh sach lenh len menu '/' cua Telegram."""
    try:
        resp = requests.post(
            _url("setMyCommands"),
            json={"commands": commands},
            timeout=15,
        )
        result = resp.json()
        if result.get("ok"):
            log(f"Da cap nhat menu Telegram ({len(commands)} lenh).")
            return True
        log(f"Khong cap nhat duoc menu Telegram: {result}")
        return False
    except requests.RequestException as e:
        log(f"Loi mang khi cap nhat menu Telegram: {e}")
        return False


def send_photo(chat_id: str, image_path: Path, caption: str = "") -> bool:
    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                _url("sendPhoto"),
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": f},
                timeout=30,
            )
        result = resp.json()
        if result.get("ok"):
            return True
        log(f"Telegram tra ve loi khi gui anh: {result}")
        return False
    except requests.RequestException as e:
        log(f"Loi mang khi gui anh: {e}")
        return False


def get_updates(offset: int, timeout: int) -> dict:
    resp = requests.post(
        _url("getUpdates"),
        data={
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": json.dumps(["message", "callback_query"]),
        },
        timeout=timeout + 10,
    )
    return resp.json()


def answer_callback_query(callback_id: str, text: str = "") -> None:
    try:
        requests.post(
            _url("answerCallbackQuery"),
            data={"callback_query_id": callback_id, "text": text},
            timeout=10,
        )
    except Exception:
        pass
