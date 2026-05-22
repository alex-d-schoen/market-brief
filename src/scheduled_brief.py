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


def _slot_label(now_local: datetime) -> tuple[str, str, str]:
    """Return (alert_type, ntfy_title_prefix, emoji_tag) for the current hour."""
    h = now_local.hour
    if h < 11:
        return "Morning Brief", "Morning Brief", "sunrise"
    if h < 17:
        return "Midday Brief", "Midday Brief", "sun_with_face"
    return "Evening Brief", "Evening Brief", "crescent_moon"


# Target Europe/Zurich local times for each brief slot.
# GH Actions cron schedules both CET and CEST UTC equivalents; this gate
# ensures only the one that lands at the right local time actually fires.
_BRIEF_SLOTS = [(7, 0), (13, 0), (22, 30)]
_SLOT_TOLERANCE_MIN = 15  # cron can be late by a few min; allow some slop


def _is_brief_time(now_local: datetime) -> bool:
    for h, m in _BRIEF_SLOTS:
        delta_min = abs((now_local.hour - h) * 60 + (now_local.minute - m))
        if delta_min <= _SLOT_TOLERANCE_MIN:
            return True
    return False


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
    alert_type, prefix, emoji = _slot_label(now_local)

    # Manual override via env (used by tests / manual triggers)
    forced = os.environ.get("BRIEF_SLOT", "").strip()
    if forced in {"Morning Brief", "Midday Brief", "Evening Brief"}:
        alert_type = prefix = forced
        emoji = {"Morning Brief": "sunrise", "Midday Brief": "sun_with_face", "Evening Brief": "crescent_moon"}[forced]

    print(f"scheduled_brief start {started.isoformat()} ({now_local.strftime('%H:%M %Z')}) → {alert_type}")

    if not forced and not _is_brief_time(now_local):
        print(f"  not within {_SLOT_TOLERANCE_MIN}min of a brief slot ({_BRIEF_SLOTS}); skipping")
        return 0

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
