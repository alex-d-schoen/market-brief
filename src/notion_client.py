"""Notion wrappers: read positions/watchlist, write & query alert log."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from notion_client import Client

from .config import (
    DEDUP_HOURS,
    NOTION_DB_ALERT_LOG,
    NOTION_DB_POSITIONS,
    NOTION_DB_WATCHLIST,
    NOTION_TOKEN,
)


@dataclass
class Position:
    ticker: str
    asset_class: str  # "Stock" | "ETF" | "Crypto"
    quantity: float | None
    entry_price: float | None
    entry_date: str | None
    currency: str | None
    thesis: str
    stop_loss: float | None
    target_price: float | None
    sector_tags: list[str] = field(default_factory=list)


@dataclass
class WatchItem:
    ticker: str
    asset_class: str
    currency: str | None
    why_watching: str
    sector_tags: list[str] = field(default_factory=list)


def _client() -> Client:
    if not NOTION_TOKEN:
        raise RuntimeError("NOTION_TOKEN not set")
    return Client(auth=NOTION_TOKEN)


# ---------- property extractors ----------

def _title(prop: dict) -> str:
    arr = prop.get("title") or []
    return "".join(t.get("plain_text", "") for t in arr).strip()


def _rich_text(prop: dict) -> str:
    arr = prop.get("rich_text") or []
    return "".join(t.get("plain_text", "") for t in arr).strip()


def _number(prop: dict) -> float | None:
    return prop.get("number")


def _select(prop: dict) -> str | None:
    sel = prop.get("select")
    return sel.get("name") if sel else None


def _multi_select(prop: dict) -> list[str]:
    return [s.get("name", "") for s in (prop.get("multi_select") or [])]


def _date(prop: dict) -> str | None:
    d = prop.get("date")
    return d.get("start") if d else None


def _url(prop: dict) -> str | None:
    return prop.get("url")


# ---------- readers ----------

def fetch_open_positions() -> list[Position]:
    notion = _client()
    out: list[Position] = []
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "database_id": NOTION_DB_POSITIONS,
            "filter": {"property": "Status", "select": {"equals": "Open"}},
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.databases.query(**kwargs)
        for row in resp["results"]:
            p = row["properties"]
            out.append(
                Position(
                    ticker=_title(p.get("Ticker", {})),
                    asset_class=_select(p.get("Asset Class", {})) or "",
                    quantity=_number(p.get("Quantity", {})),
                    entry_price=_number(p.get("Entry Price", {})),
                    entry_date=_date(p.get("Entry Date", {})),
                    currency=_select(p.get("Currency", {})),
                    thesis=_rich_text(p.get("Thesis", {})),
                    stop_loss=_number(p.get("Stop Loss", {})),
                    target_price=_number(p.get("Target Price", {})),
                    sector_tags=_multi_select(p.get("Sector Tags", {})),
                )
            )
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return out


def fetch_active_watchlist() -> list[WatchItem]:
    notion = _client()
    out: list[WatchItem] = []
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "database_id": NOTION_DB_WATCHLIST,
            "filter": {"property": "Status", "select": {"equals": "Active"}},
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.databases.query(**kwargs)
        for row in resp["results"]:
            p = row["properties"]
            out.append(
                WatchItem(
                    ticker=_title(p.get("Ticker", {})),
                    asset_class=_select(p.get("Asset Class", {})) or "",
                    currency=_select(p.get("Currency", {})),
                    why_watching=_rich_text(p.get("Why Watching", {})),
                    sector_tags=_multi_select(p.get("Sector Tags", {})),
                )
            )
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return out


# ---------- alert log: dedup readers ----------

def recent_price_alert_tickers(hours: int = DEDUP_HOURS) -> set[str]:
    """Tickers with a Price Alert logged in the last `hours`."""
    notion = _client()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    tickers: set[str] = set()
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "database_id": NOTION_DB_ALERT_LOG,
            "filter": {
                "and": [
                    {"property": "Type", "select": {"equals": "Price Alert"}},
                    {"property": "Timestamp", "date": {"on_or_after": since}},
                ]
            },
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.databases.query(**kwargs)
        for row in resp["results"]:
            p = row["properties"]
            t = _rich_text(p.get("Ticker", {}))
            if t:
                tickers.add(t)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return tickers


def recent_news_urls(hours: int = 24) -> set[str]:
    """URLs of News Alerts logged in the last `hours` (default 24h window)."""
    notion = _client()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    urls: set[str] = set()
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "database_id": NOTION_DB_ALERT_LOG,
            "filter": {
                "and": [
                    {"property": "Type", "select": {"equals": "News Alert"}},
                    {"property": "Timestamp", "date": {"on_or_after": since}},
                ]
            },
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.databases.query(**kwargs)
        for row in resp["results"]:
            p = row["properties"]
            u = _url(p.get("Source URL", {}))
            if u:
                urls.add(u)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return urls


# ---------- alert log: writer ----------

def log_alert(
    *,
    title: str,
    alert_type: str,  # "Price Alert" | "News Alert" | "Morning Brief" | "Midday Brief" | "Evening Brief"
    ticker: str = "",
    message: str = "",
    source_url: str | None = None,
    move_pct: float | None = None,
    atr_ratio: float | None = None,
    timestamp: datetime | None = None,
) -> None:
    notion = _client()
    ts = (timestamp or datetime.now(timezone.utc)).isoformat()

    props: dict[str, Any] = {
        "Title": {"title": [{"text": {"content": title[:2000]}}]},
        "Timestamp": {"date": {"start": ts}},
        "Type": {"select": {"name": alert_type}},
    }
    if ticker:
        props["Ticker"] = {"rich_text": [{"text": {"content": ticker}}]}
    if message:
        props["Message"] = {"rich_text": [{"text": {"content": message[:2000]}}]}
    if source_url:
        props["Source URL"] = {"url": source_url}
    if move_pct is not None:
        props["Move %"] = {"number": round(float(move_pct), 4)}
    if atr_ratio is not None:
        props["ATR Ratio"] = {"number": round(float(atr_ratio), 4)}

    notion.pages.create(parent={"database_id": NOTION_DB_ALERT_LOG}, properties=props)
