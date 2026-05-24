"""Scheduled brief entrypoint.

Cron: 07:00 / 13:00 / 22:30 Europe/Zurich.

Flow:
  1. Read positions + watchlist.
  2. Pull live snapshot per asset (current price, day move, ATR ratio).
  3. Pull market wires (WSJ + MarketWatch top headlines).
  4. Earnings: skipped — Finnhub /calendar/earnings is paid; punt to v2.
  5. Compose ~350-word brief via Claude.
  6. ntfy push + log.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .atr import atr_from_closes, atr_from_ohlc, materiality_ratio
from .claude import compose_brief
from .config import TZ
from .market_data import fetch_crypto, fetch_stock, is_stock_data_fresh
from .news import fetch_market_wires
from .notion_client import fetch_active_watchlist, fetch_open_positions, log_alert
from .ntfy import push


@dataclass
class AssetLine:
    ticker: str
    asset_class: str
    current: float
    move_pct: float
    ratio: float
    note: str = ""


_SLOT_META = {
    "Morning Brief": ("Morning Brief", "sunrise"),
    "Midday Brief": ("Midday Brief", "sun_with_face"),
    "Evening Brief": ("Evening Brief", "crescent_moon"),
}


def _slot_label(now_local: datetime) -> tuple[str, str, str]:
    """Fallback: guess the slot from local hour. Used for manual CLI runs."""
    h = now_local.hour
    if h < 11:
        return "Morning Brief", *_SLOT_META["Morning Brief"]
    if h < 17:
        return "Midday Brief", *_SLOT_META["Midday Brief"]
    return "Evening Brief", *_SLOT_META["Evening Brief"]


# Map the cron expression that triggered the GH Actions run to (slot_label,
# UTC offset hours the cron assumes). Each slot has two crons — one for CET
# (UTC+1, winter) and one for CEST (UTC+2, summer) — and only the one that
# matches the current DST offset should fire.
_CRON_TO_SLOT: dict[str, tuple[str, int]] = {
    "0 6 * * *":   ("Morning Brief", 1),
    "0 5 * * *":   ("Morning Brief", 2),
    "0 12 * * *":  ("Midday Brief", 1),
    "0 11 * * *":  ("Midday Brief", 2),
    "30 21 * * *": ("Evening Brief", 1),
    "30 20 * * *": ("Evening Brief", 2),
}


def _slot_from_cron(cron: str, now_local: datetime) -> tuple[str, str, str] | None:
    """Resolve the cron expression to (alert_type, prefix, emoji), or None if
    this cron is for the other DST season (and so should be skipped today).

    Using the triggering cron instead of wall-clock time avoids GH Actions
    free-tier cron drift (frequently 1-3 hours) eating every scheduled run.
    """
    entry = _CRON_TO_SLOT.get(cron.strip())
    if entry is None:
        return None
    slot, cron_offset = entry
    offset = now_local.utcoffset()
    if offset is None or int(offset.total_seconds() // 3600) != cron_offset:
        return None
    prefix, emoji = _SLOT_META[slot]
    return slot, prefix, emoji


def _snapshot_stock(ticker: str) -> AssetLine | None:
    snap = fetch_stock(ticker)
    if len(snap.bars) < 15:
        return AssetLine(ticker, "Stock", snap.current_price, 0.0, 0.0, "insufficient history")
    atr = atr_from_ohlc(snap.bars, n=14)
    atr_pct = atr / snap.current_price * 100
    move = (snap.current_price - snap.today_open) / snap.today_open * 100
    note = "" if is_stock_data_fresh(snap) else f"stale (last bar {snap.last_bar_date})"
    return AssetLine(
        ticker=ticker,
        asset_class="Stock",
        current=snap.current_price,
        move_pct=move,
        ratio=materiality_ratio(move, atr_pct),
        note=note,
    )


def _snapshot_crypto(coin_id: str) -> AssetLine | None:
    snap = fetch_crypto(coin_id)
    if len(snap.closes) < 15:
        return AssetLine(coin_id, "Crypto", snap.current_price, 0.0, 0.0, "insufficient history")
    atr = atr_from_closes(snap.closes, n=14)
    atr_pct = atr / snap.current_price * 100
    move = (snap.current_price - snap.prev_close) / snap.prev_close * 100
    return AssetLine(
        ticker=coin_id,
        asset_class="Crypto",
        current=snap.current_price,
        move_pct=move,
        ratio=materiality_ratio(move, atr_pct),
    )


def _snapshot(ticker: str, asset_class: str) -> AssetLine | None:
    try:
        if asset_class.lower() == "crypto":
            return _snapshot_crypto(ticker)
        return _snapshot_stock(ticker)
    except Exception as e:
        print(f"  [{ticker}] snapshot error: {e!r}")
        return None


def _format_lines(lines: list[AssetLine]) -> str:
    out = []
    for ln in lines:
        suffix = f" — {ln.note}" if ln.note else ""
        out.append(
            f"{ln.ticker} ({ln.asset_class}): {ln.current:.2f}  "
            f"move {ln.move_pct:+.2f}%  ATR ratio {ln.ratio:.2f}{suffix}"
        )
    return "\n".join(out)


def run() -> int:
    started = datetime.now(timezone.utc)
    now_local = started.astimezone(ZoneInfo(TZ))

    forced = os.environ.get("BRIEF_SLOT", "").strip()
    triggering_cron = os.environ.get("TRIGGERING_CRON", "").strip()

    if forced in _SLOT_META:
        alert_type = forced
        prefix, emoji = _SLOT_META[forced]
    elif triggering_cron:
        resolved = _slot_from_cron(triggering_cron, now_local)
        if resolved is None:
            print(
                f"scheduled_brief start {started.isoformat()} "
                f"({now_local.strftime('%H:%M %Z')}) — cron {triggering_cron!r} "
                f"is for the off-season DST variant; skipping"
            )
            return 0
        alert_type, prefix, emoji = resolved
    else:
        alert_type, prefix, emoji = _slot_label(now_local)

    print(f"scheduled_brief start {started.isoformat()} ({now_local.strftime('%H:%M %Z')}) → {alert_type}")

    positions = fetch_open_positions()
    watchlist = fetch_active_watchlist()
    print(f"  positions: {len(positions)}  watchlist: {len(watchlist)}")

    pos_lines = [s for s in (_snapshot(p.ticker, p.asset_class) for p in positions) if s is not None]
    watch_lines = [s for s in (_snapshot(w.ticker, w.asset_class) for w in watchlist) if s is not None]

    wires = fetch_market_wires(max_items=10)
    market_block = "\n".join(f"- {w.title} ({w.source})" for w in wires) if wires else ""

    brief = compose_brief(
        time_label=alert_type,
        positions_block=_format_lines(pos_lines),
        watchlist_block=_format_lines(watch_lines),
        earnings_block="",  # TODO: hook up a free earnings calendar later
        market_pulse_block=market_block,
    )

    push(brief, title=prefix, priority=3, tags=[emoji])
    log_alert(
        title=f"{prefix} {now_local.strftime('%Y-%m-%d %H:%M %Z')}",
        alert_type=alert_type,
        message=brief,
    )

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"scheduled_brief done in {elapsed:.1f}s")
    print("---")
    print(brief)
    return 0


if __name__ == "__main__":
    sys.exit(run())
