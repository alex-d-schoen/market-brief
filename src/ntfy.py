"""ntfy.sh push notifications.

POST to https://ntfy.sh/<topic> with the body as the message and headers for
title/priority/tags/click. See https://docs.ntfy.sh/publish/.

ntfy headers must be ASCII; we use RFC 2047 encoded-words for Unicode titles
(per ntfy docs: https://docs.ntfy.sh/publish/#unicode-characters).
"""
from __future__ import annotations

import base64
from typing import Iterable

import requests

from .config import NTFY_TOPIC

NTFY_BASE = "https://ntfy.sh"


def _encode_header(value: str) -> str:
    """Pass through ASCII; RFC 2047 base64-encode if non-ASCII."""
    try:
        value.encode("latin-1")
        return value
    except UnicodeEncodeError:
        b64 = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return f"=?utf-8?B?{b64}?="


def push(
    message: str,
    *,
    title: str | None = None,
    priority: int = 3,         # 1 min, 3 default, 4 high (loud), 5 max
    tags: Iterable[str] | None = None,  # emoji shortcodes: chart_with_upwards_trend, etc.
    click: str | None = None,  # URL to open on tap
    topic: str | None = None,
    timeout: float = 10.0,
) -> None:
    t = topic or NTFY_TOPIC
    if not t:
        raise RuntimeError("NTFY_TOPIC not set")

    headers: dict[str, str] = {"Priority": str(priority)}
    if title:
        headers["Title"] = _encode_header(title)
    if tags:
        headers["Tags"] = ",".join(tags)
    if click:
        headers["Click"] = click

    r = requests.post(
        f"{NTFY_BASE}/{t}",
        data=message.encode("utf-8"),
        headers=headers,
        timeout=timeout,
    )
    r.raise_for_status()
