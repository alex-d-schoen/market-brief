"""ATR (Average True Range) computation.

Spec: simple arithmetic mean of last 14 True Ranges (not Wilder's smoothing).
"""
from __future__ import annotations

from typing import Sequence, TypedDict


class Bar(TypedDict):
    high: float
    low: float
    close: float


def atr_from_ohlc(bars: Sequence[Bar], n: int = 14) -> float:
    """True ATR from daily OHLC bars sorted ascending by date.

    TR_i = max(high_i - low_i, |high_i - close_{i-1}|, |low_i - close_{i-1}|)
    ATR = mean of last n TRs.
    """
    if len(bars) < 2:
        raise ValueError(f"need at least 2 bars for ATR, got {len(bars)}")
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, l = bars[i]["high"], bars[i]["low"]
        pc = bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-n:]
    return sum(window) / len(window)


def atr_from_closes(closes: Sequence[float], n: int = 14) -> float:
    """ATR proxy from close-to-close changes (used for crypto, no intraday OHLC).

    TR_i ≈ |close_i - close_{i-1}|. Documented approximation per spec.
    """
    if len(closes) < 2:
        raise ValueError(f"need at least 2 closes for ATR, got {len(closes)}")
    diffs = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    window = diffs[-n:]
    return sum(window) / len(window)


def materiality_ratio(current_move_pct: float, atr_pct: float) -> float:
    """|move%| / atr%. >1.5 means material per default threshold."""
    if atr_pct <= 0:
        return 0.0
    return abs(current_move_pct) / atr_pct
