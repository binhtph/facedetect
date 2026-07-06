"""Telegram Bot notification support for IRIS."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class TelegramError(Exception):
    """Raised when a Telegram API call fails."""


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


def _api_call(token: str, method: str, payload: dict | None = None, files: dict | None = None) -> dict:
    """Call the Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/{method}"

    if files:
        boundary = "----IRISBoundary"
        body = b""
        for key, value in (payload or {}).items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
            body += f"{value}\r\n".encode()
        for key, (filename, data, content_type) in files.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
            body += f"Content-Type: {content_type}\r\n\r\n".encode()
            body += data + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    elif payload:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
    else:
        req = urllib.request.Request(url)

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get("description", str(error))
        except Exception:
            detail = str(error)
        raise TelegramError(f"Telegram API error: {detail}") from error
    except urllib.error.URLError as error:
        raise TelegramError(f"Cannot reach Telegram API: {error}") from error

    if not result.get("ok"):
        raise TelegramError(result.get("description", "Unknown Telegram error"))
    return result


def test_connection(config: TelegramConfig) -> dict:
    """Test the bot token and send a test message."""
    if not config.configured:
        raise TelegramError("Telegram bot token and chat ID are required.")
    result = _api_call(config.bot_token, "getMe")
    bot_name = result.get("result", {}).get("username", "unknown")
    _api_call(
        config.bot_token,
        "sendMessage",
        {
            "chat_id": config.chat_id,
            "text": f"[OK] IRIS Face Recognition connected!\nBot: @{bot_name}",
            "parse_mode": "HTML",
        },
    )
    return {"ok": True, "bot_username": bot_name}


def send_recognition_alert(
    config: TelegramConfig,
    person_name: str,
    confidence: float,
    event_type: str,
    camera_name: str,
    event_time: str,
    image_path: str | None = None,
) -> None:
    """Send a recognition notification to Telegram."""
    if not config.configured:
        return

    prefix = {
        "known": "[OK]",
        "review": "[Review]",
        "unknown": "[Alert]",
        "no_face": "[No face]",
        "skipped": "[Skipped]",
        "error": "[Error]",
        "processing": "[Processing]",
    }.get(event_type, "[Info]")
    type_label = {
        "known": "Recognized",
        "review": "Needs Review",
        "unknown": "Unknown Visitor",
        "no_face": "No Face Detected",
        "skipped": "Skipped Cooldown",
        "error": "Processing Failed",
        "processing": "Processing",
    }.get(event_type, event_type)

    text = (
        f"{prefix} <b>{type_label}</b>\n"
        f"Person: {person_name}\n"
        f"Camera: {camera_name}\n"
    )
    if confidence > 0:
        text += f"Confidence: {confidence:.1f}%\n"
    text += f"Time: {event_time}"

    try:
        if image_path:
            abs_path = Path(image_path)
            if abs_path.exists():
                data = abs_path.read_bytes()
                ext = abs_path.suffix.lower()
                content_type = "image/png" if ext == ".png" else "image/jpeg"
                _api_call(
                    config.bot_token,
                    "sendPhoto",
                    {"chat_id": config.chat_id, "caption": text, "parse_mode": "HTML"},
                    {"photo": (abs_path.name, data, content_type)},
                )
                return

        _api_call(
            config.bot_token,
            "sendMessage",
            {"chat_id": config.chat_id, "text": text, "parse_mode": "HTML"},
        )
    except TelegramError:
        # Do not block recognition if Telegram delivery fails.
        pass
