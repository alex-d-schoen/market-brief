"""News monitor entrypoint.

Cron: every 10 min, 24/7.

Flow:
  1. Read positions + watchlist from Notion.
  2. Pull Yahoo per-ticker RSS (skip crypto — no Yahoo coverage).
  3. Filter to items younger than NEWS_FRESHNESS_MIN.
  4. Dedup by URL against Alert Log (last 24h).
  5. Send each new item to Claude for materiality decision.
  6. If material → ntfy push with click URL.
  7. Always log to Notion (material or filtered).
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone

from .claude import filter_news
from .config import NEWS_FRESHNESS_MIN
from .news import NewsItem, collect_ticker_news
from .notion_client import (
    fetch_active_watchlist,
    fetch_open_positions,
    log_alert,
    recent_news_urls,
)
from .ntfy import push


def _classify_index(positions, watchlist) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Return (asset_class_by_ticker, thesis_by_ticker, position_flag_by_ticker)."""
    asset_class: dict[str, str] = {}
    thesis: dict[str, str] = {}
    is_pos: dict[str, str] = {}
    for p in positions:
        asset_class[p.ticker] = p.asset_class
        thesis[p.ticker] = p.thesis or ""
        is_pos[p.ticker] = "yes"
    for w in watchlist:
        # don't overwrite a position entry of the same ticker
        asset_class.setdefault(w.ticker, w.asset_class)
        is_pos.setdefault(w.ticker, "no")
    return asset_class, thesis, is_pos


def _handle_item(item: NewsItem, asset_class: str, is_position: bool, thesis: str | None) -> None:
    try:
        decision = filter_news(
            ticker=item.ticker or "",
            asset_class=asset_class,
            headline=item.title,
            summary=item.summary,
            is_position=is_position,
            thesis=thesis if is_position else None,
        )
    except Exception as e:
        print(f"  [{item.ticker}] Claude filter error: {e!r}")
        traceback.print_exc(limit=2)
        return

    material = bool(decision.get("material"))
    impact = decision.get("thesis_impact", "N/A")
    text = decision.get("alert_text", item.title)

    title = f"{item.ticker} 📰 {item.title[:60]}"

    if material:
        try:
            push(text, title=title, priority=4, tags=["newspaper"], click=item.url)
        except Exception as e:
            print(f"  [{item.ticker}] ntfy push error: {e!r}")

    try:
        log_alert(
            title=title,
            alert_type="News Alert",
            ticker=item.ticker or "",
            message=f"[{'MATERIAL' if material else 'filtered'}] impact={impact}\n{text}",
            source_url=item.url,
        )
    except Exception as e:
        print(f"  [{item.ticker}] Notion log error: {e!r}")

    flag = "MATERIAL" if material else "filter"
    print(f"  [{item.ticker}] {flag} ({impact}) :: {item.title[:80]}")


def run() -> int:
    started = datetime.now(timezone.utc)
    print(f"news_monitor start {started.isoformat()}")

    positions = fetch_open_positions()
    watchlist = fetch_active_watchlist()
    print(f"  positions: {len(positions)}  watchlist: {len(watchlist)}")

    asset_class, thesis, is_pos = _classify_index(positions, watchlist)
    tickers = list(asset_class.keys())

    items = collect_ticker_news(
        tickers,
        max_age_min=NEWS_FRESHNESS_MIN,
        skip_asset_classes={"crypto"},
        classes_by_ticker=asset_class,
    )
    print(f"  RSS items in last {NEWS_FRESHNESS_MIN}m: {len(items)}")

    if not items:
        print("news_monitor done — no fresh items")
        return 0

    seen_urls = recent_news_urls(hours=24)
    fresh = [i for i in items if i.url not in seen_urls]
    print(f"  after URL dedup: {len(fresh)}")

    for item in fresh:
        ac = asset_class.get(item.ticker or "", "Stock")
        is_position = is_pos.get(item.ticker or "", "no") == "yes"
        th = thesis.get(item.ticker or "") if is_position else None
        _handle_item(item, ac, is_position, th)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"news_monitor done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(run())
