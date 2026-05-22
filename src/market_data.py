"""Market data fetchers: stocks via yfinance, crypto via CoinGecko free."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Sequence

import requests
import yfinance as yf

from .atr import Bar


COINGECKO_BASE = "https://api.coingecko.com/api/v3"
USER_AGENT = "market-brief/0.1 (+https://github.com)"


@dataclass
class StockSnapshot:
    ticker: str
    current_price: float
    today_open: float
    last_bar_date: date  # date of most recent OHLC bar
    bars: list[Bar]      # historical bars, oldest first, includes today if trading


@dataclass
class CryptoSnapshot:
    coin_id: str
    current_price: float
    prev_close: float    # yesterday's close, used as "today open" proxy per spec
    closes: list[float]  # daily closes oldest first, includes today's running price as last


def fetch_stock(ticker: str, lookback_days: int = 25) -> StockSnapshot:
    """Pull ~lookback_days of daily OHLC + current quote from Yahoo.

    Returns at least 15 bars so 14-day ATR is computable (1 prior + 14 TRs).
    """
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{lookback_days}d", auto_adjust=False)
    if hist.empty:
        raise RuntimeError(f"no history for {ticker}")

    bars: list[Bar] = [
        Bar(high=float(row.High), low=float(row.Low), close=float(row.Close))
        for row in hist.itertuples()
    ]

    last_bar = hist.iloc[-1]
    last_bar_date = hist.index[-1].date()

    # Current price: prefer fast_info live quote, fall back to last close
    current_price = float(last_bar.Close)
    try:
        fi = t.fast_info
        lp = fi.last_price if hasattr(fi, "last_price") else fi["last_price"]
        if lp:
            current_price = float(lp)
    except Exception:
        pass

    today_open = float(last_bar.Open)

    return StockSnapshot(
        ticker=ticker,
        current_price=current_price,
        today_open=today_open,
        last_bar_date=last_bar_date,
        bars=bars,
    )


def fetch_crypto(coin_id: str, lookback_days: int = 20, vs_currency: str = "usd") -> CryptoSnapshot:
    """Pull ~lookback_days of daily closes + current price from CoinGecko free.

    Endpoint /coins/{id}/market_chart returns close-only (no OHLC) on free tier.
    """
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    r = requests.get(
        url,
        params={"vs_currency": vs_currency, "days": lookback_days, "interval": "daily"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    points = data.get("prices") or []
    if len(points) < 2:
        raise RuntimeError(f"no/insufficient price history for {coin_id}: {len(points)} points")

    closes = [float(p[1]) for p in points]

    # Live current price (separate endpoint for freshness)
    pr = requests.get(
        f"{COINGECKO_BASE}/simple/price",
        params={"ids": coin_id, "vs_currencies": vs_currency},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=15,
    )
    pr.raise_for_status()
    cur = pr.json().get(coin_id, {}).get(vs_currency)
    current_price = float(cur) if cur is not None else closes[-1]

    # Spec: use yesterday's close as "today open" proxy
    prev_close = closes[-2]

    return CryptoSnapshot(
        coin_id=coin_id,
        current_price=current_price,
        prev_close=prev_close,
        closes=closes,
    )


def is_stock_data_fresh(snap: StockSnapshot, today_utc: date | None = None) -> bool:
    """True if the latest bar is today's session (UTC date).

    Used by price_monitor to skip alerts on closed-market stale data.
    """
    today_utc = today_utc or datetime.now(timezone.utc).date()
    return snap.last_bar_date >= today_utc
