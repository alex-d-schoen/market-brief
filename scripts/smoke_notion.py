"""Manual smoke test for Notion reads.

Usage:
    export NOTION_TOKEN=ntn_xxx
    python -m scripts.smoke_notion

Verifies the integration can see all 3 databases and returns the row counts.
"""
from src.notion_client import (
    fetch_open_positions,
    fetch_active_watchlist,
    recent_price_alert_tickers,
    recent_news_urls,
)


def main() -> None:
    positions = fetch_open_positions()
    print(f"Open positions: {len(positions)}")
    for p in positions:
        print(f"  - {p.ticker} ({p.asset_class}) qty={p.quantity} entry={p.entry_price} {p.currency}")

    watchlist = fetch_active_watchlist()
    print(f"\nActive watchlist: {len(watchlist)}")
    for w in watchlist:
        print(f"  - {w.ticker} ({w.asset_class}) {w.currency}")

    recent_tickers = recent_price_alert_tickers()
    print(f"\nPrice alerts in last 4h: {len(recent_tickers)} ({sorted(recent_tickers)})")

    recent_urls = recent_news_urls()
    print(f"News alerts in last 24h: {len(recent_urls)} URLs")


if __name__ == "__main__":
    main()
