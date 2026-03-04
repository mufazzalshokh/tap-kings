"""
Telegram Mini App initData validation.
HMAC-SHA256 — exactly what APEX PLAY requires in their must-have list.
Docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import os
from urllib.parse import unquote, parse_qsl

from fastapi import HTTPException, Header
from typing import Optional


BOT_TOKEN = os.getenv("BOT_TOKEN", "")


def validate_init_data(init_data: str) -> dict:
    """
    Validates Telegram WebApp initData using HMAC-SHA256.
    Returns parsed user dict if valid, raises HTTPException if not.
    """
    try:
        parsed = dict(parse_qsl(unquote(init_data), keep_blank_values=True))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid initData format")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash in initData")

    # Build data-check-string: sorted key=value pairs joined by \n
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    # Secret key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()

    # Compute expected hash
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData signature")

    # Parse user from validated data
    user_str = parsed.get("user", "{}")
    try:
        user = json.loads(user_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=401, detail="Invalid user data")

    return user


async def get_current_user(
    x_init_data: Optional[str] = Header(None)
) -> dict:
    """
    FastAPI dependency — validates initData from X-Init-Data header.
    Use as: user = Depends(get_current_user)
    In development (no BOT_TOKEN), returns mock user.
    """
    if not BOT_TOKEN or os.getenv("DEV_MODE") == "true":
        # Dev mode — return mock user for local testing
        return {
            "id": 123456789,
            "first_name": "Dev",
            "last_name": "User",
            "username": "devuser"
        }

    if not x_init_data:
        raise HTTPException(
            status_code=401,
            detail="X-Init-Data header required"
        )

    return validate_init_data(x_init_data)
