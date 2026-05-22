"""RSS feed parsers: Yahoo per-ticker + market wires (WSJ, MarketWatch)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import feedparser
from dateutil import parser as dateparser


@dataclass
class NewsItem:
    ticker: str | None       # None for general market wires
    title: str
    summary: str
    url: str
    published: datetime      # tz-aware UTC
    source: str


def _parse_published(entry: dict) -> datetime | None:
    """Try several fields Yahoo / WSJ / MarketWatch use."""
    for key in ("published", "updated", "pubDate"):
        val = entry.get(key)
        if val:
            try:
                dt = dateparser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, TypeError):
                continue
    # struct_time fallback
    pt = entry.get("published_parsed") or entry.get("updated_parsed")
    if pt:
        return datetime(*pt[:6], tzinfo=timezone.utc)
    return None


def _ticker_relevant(ticker: str, title: str, summary: str) -> bool:
    """Cheap relevance check: ticker symbol OR company root must appear in title/summary.

    Drops sector-tangent items Yahoo's per-ticker feed sometimes includes.
    """
    text = f"{title}\n{summary}".upper()
    bare = ticker.upper().split(".")[0]  # UBSG.SW → UBSG
    if bare in text:
        return True
    # Company-name hints for common tickers without obvious symbols in headlines
    NAME_HINTS = {
        "AAPL": ("APPLE", "IPHONE", "IPAD"),
        "NVDA": ("NVIDIA",),
        "MSFT": ("MICROSOFT",),
        "GOOG": ("GOOGLE", "ALPHABET"),
        "GOOGL": ("GOOGLE", "ALPHABET"),
        "META": ("META", "FACEBOOK", "INSTAGRAM"),
        "TSLA": ("TESLA",),
        "AMZN": ("AMAZON",),
        "UBSG": ("UBS",),
    }
    for hint in NAME_HINTS.get(bare, ()):
        if hint in text:
            return True
    return False


def fetch_yahoo_ticker_rss(ticker: str, max_age_min: int) -> list[NewsItem]:
    """Per-ticker headlines from Yahoo Finance, filtered to last `max_age_min` minutes
    AND requiring the ticker / company name to appear in the headline or summary."""
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_min)
    out: list[NewsItem] = []
    for entry in feed.entries:
        pub = _parse_published(entry)
        if pub is None or pub < cutoff:
            continue
        link = entry.get("link") or ""
        if not link:
            continue
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or "").strip()
        if not _ticker_relevant(ticker, title, summary):
            continue
        out.append(NewsItem(
            ticker=ticker,
            title=title,
            summary=summary,
            url=link,
            published=pub,
            source="yahoo",
        ))
    return out


def fetch_market_wires(max_items: int = 15) -> list[NewsItem]:
    """Top market headlines from WSJ + MarketWatch RSS. Used by scheduled brief."""
    feeds = [
        ("wsj", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
        ("marketwatch", "https://www.marketwatch.com/rss/topstories"),
    ]
    out: list[NewsItem] = []
    for source, url in feeds:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            pub = _parse_published(entry) or datetime.now(timezone.utc)
            out.append(NewsItem(
                ticker=None,
                title=(entry.get("title") or "").strip(),
                summary=(entry.get("summary") or "").strip(),
                url=(entry.get("link") or "").strip(),
                published=pub,
                source=source,
            ))
    out.sort(key=lambda x: x.published, reverse=True)
    return out[:max_items]


def collect_ticker_news(
    tickers: Iterable[str],
    *,
    max_age_min: int,
    skip_asset_classes: Iterable[str] = (),
    classes_by_ticker: dict[str, str] | None = None,
) -> list[NewsItem]:
    """Run Yahoo lookups for each ticker. Skips tickers whose asset class is in skip_asset_classes."""
    skip = {c.lower() for c in skip_asset_classes}
    classes = classes_by_ticker or {}
    items: list[NewsItem] = []
    for t in tickers:
        if classes.get(t, "").lower() in skip:
            continue
        try:
            items.extend(fetch_yahoo_ticker_rss(t, max_age_min=max_age_min))
        except Exception as e:
            print(f"  [{t}] RSS error: {e!r}")
    return items
