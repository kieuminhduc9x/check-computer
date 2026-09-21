"""
telegram_api.py - Lop giao tiep voi Telegram Bot API.
Dung thu vien `requests` cho don gian va de xu ly upload anh (multipart).
"""

import json
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


def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    try:
        resp = requests.post(
            _url("sendMessage"),
            data={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
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
            "allowed_updates": json.dumps(["message"]),
        },
        timeout=timeout + 10,
    )
    return resp.json()


def get_me() -> dict:
    resp = requests.get(_url("getMe"), timeout=15)
    return resp.json()
