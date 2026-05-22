"""Price monitor entrypoint.

Cron: every 10 min, 24/7 (GitHub Actions).

Flow:
  1. Read Open positions + Active watchlist from Notion.
  2. For each asset, fetch current price + 14d history.
  3. Compute ATR + materiality ratio.
  4. If ratio > MATERIAL_THRESHOLD and not deduped, compose with Claude.
  5. ntfy push + log to Notion Alert Log.
  6. Always log filtered/errored attempts to a single combined Notion row? No —
     spec says log every alert; filtered moves stay in process logs only.
"""
from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone

from .atr import atr_from_closes, atr_from_ohlc, materiality_ratio
from .claude import compose_price_alert
from .config import MATERIAL_THRESHOLD
from .market_data import (
    StockSnapshot,
    fetch_crypto,
    fetch_stock,
    is_stock_data_fresh,
)
from .notion_client import (
    Position,
    WatchItem,
    fetch_active_watchlist,
    fetch_open_positions,
    log_alert,
    recent_price_alert_tickers,
)
from .ntfy import push


@dataclass
class Eval:
    ticker: str
    asset_class: str
    is_position: bool
    thesis: str | None
    current_price: float
    move_pct: float
    atr_pct: float
    ratio: float


def _is_crypto(asset_class: str) -> bool:
    return asset_class.lower() == "crypto"


def _evaluate_stock(ticker: str, asset_class: str, is_position: bool, thesis: str | None) -> Eval | None:
    snap: StockSnapshot = fetch_stock(ticker)
    if not is_stock_data_fresh(snap):
        print(f"  [{ticker}] stale (last bar {snap.last_bar_date}); skipping")
        return None
    if len(snap.bars) < 15:
        print(f"  [{ticker}] only {len(snap.bars)} bars; need 15+ for ATR; skipping")
        return None

    atr = atr_from_ohlc(snap.bars, n=14)
    atr_pct = atr / snap.current_price * 100
    move_pct = (snap.current_price - snap.today_open) / snap.today_open * 100
    ratio = materiality_ratio(move_pct, atr_pct)
    return Eval(
        ticker=ticker,
        asset_class=asset_class,
        is_position=is_position,
        thesis=thesis,
        current_price=snap.current_price,
        move_pct=move_pct,
        atr_pct=atr_pct,
        ratio=ratio,
    )


def _evaluate_crypto(coin_id: str, asset_class: str, is_position: bool, thesis: str | None) -> Eval | None:
    snap = fetch_crypto(coin_id)
    if len(snap.closes) < 15:
        print(f"  [{coin_id}] only {len(snap.closes)} closes; skipping")
        return None
    atr = atr_from_closes(snap.closes, n=14)
    atr_pct = atr / snap.current_price * 100
    move_pct = (snap.current_price - snap.prev_close) / snap.prev_close * 100
    ratio = materiality_ratio(move_pct, atr_pct)
    return Eval(
        ticker=coin_id,
        asset_class=asset_class,
        is_position=is_position,
        thesis=thesis,
        current_price=snap.current_price,
        move_pct=move_pct,
        atr_pct=atr_pct,
        ratio=ratio,
    )


def _evaluate(item: Position | WatchItem, is_position: bool) -> Eval | None:
    thesis = item.thesis if is_position else None  # type: ignore[attr-defined]
    try:
        if _is_crypto(item.asset_class):
            return _evaluate_crypto(item.ticker, item.asset_class, is_position, thesis)
        return _evaluate_stock(item.ticker, item.asset_class, is_position, thesis)
    except Exception as e:
        print(f"  [{item.ticker}] eval error: {e!r}")
        traceback.print_exc(limit=2)
        return None


def _send_alert(ev: Eval) -> None:
    msg = compose_price_alert(
        ticker=ev.ticker,
        move_pct=ev.move_pct,
        atr_ratio=ev.ratio,
        asset_class=ev.asset_class,
        is_position=ev.is_position,
        thesis=ev.thesis,
    )
    emoji = "chart_with_upwards_trend" if ev.move_pct >= 0 else "chart_with_downwards_trend"
    title = f"{ev.ticker} {ev.move_pct:+.2f}%"
    push(msg, title=title, priority=4, tags=[emoji])
    log_alert(
        title=title,
        alert_type="Price Alert",
        ticker=ev.ticker,
        message=msg,
        move_pct=ev.move_pct,
        atr_ratio=ev.ratio,
    )
    print(f"  [{ev.ticker}] ALERTED ratio={ev.ratio:.2f} move={ev.move_pct:+.2f}%")


def run() -> int:
    started = datetime.now(timezone.utc)
    print(f"price_monitor start {started.isoformat()}")

    positions = fetch_open_positions()
    watchlist = fetch_active_watchlist()
    print(f"  positions: {len(positions)}  watchlist: {len(watchlist)}")

    recent = recent_price_alert_tickers()
    if recent:
        print(f"  deduped (last 4h): {sorted(recent)}")

    alerted = 0
    evaluated = 0
    items: list[tuple[object, bool]] = [(p, True) for p in positions] + [(w, False) for w in watchlist]

    for item, is_position in items:
        ev = _evaluate(item, is_position)  # type: ignore[arg-type]
        if ev is None:
            continue
        evaluated += 1
        flag = "*" if ev.ratio > MATERIAL_THRESHOLD else " "
        print(f"  {flag} {ev.ticker:<10} move={ev.move_pct:+6.2f}%  ATR%={ev.atr_pct:5.2f}  ratio={ev.ratio:4.2f}")

        if ev.ratio <= MATERIAL_THRESHOLD:
            continue
        if ev.ticker in recent:
            print(f"  [{ev.ticker}] material but deduped (4h)")
            continue

        try:
            _send_alert(ev)
            alerted += 1
        except Exception as e:
            print(f"  [{ev.ticker}] alert send failed: {e!r}")
            traceback.print_exc(limit=2)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"price_monitor done in {elapsed:.1f}s — evaluated {evaluated}, alerted {alerted}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
