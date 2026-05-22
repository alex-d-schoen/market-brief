"""Manual smoke test for market data + ATR.

Usage:
    python -m scripts.smoke_market

Pulls AAPL (stock) and bitcoin (crypto), prints ATR and materiality ratio.
"""
from src.atr import atr_from_closes, atr_from_ohlc, materiality_ratio
from src.market_data import fetch_crypto, fetch_stock


def main() -> None:
    print("=== AAPL (stock) ===")
    s = fetch_stock("AAPL")
    atr = atr_from_ohlc(s.bars, n=14)
    atr_pct = atr / s.current_price * 100
    move_pct = (s.current_price - s.today_open) / s.today_open * 100
    ratio = materiality_ratio(move_pct, atr_pct)
    print(f"  bars: {len(s.bars)}  last bar: {s.last_bar_date}")
    print(f"  current: {s.current_price:.2f}  today_open: {s.today_open:.2f}")
    print(f"  ATR (14d): {atr:.4f}  ATR%: {atr_pct:.3f}%")
    print(f"  move: {move_pct:+.3f}%  ratio: {ratio:.2f}  material: {ratio > 1.5}")

    print("\n=== bitcoin (crypto) ===")
    c = fetch_crypto("bitcoin")
    atr_c = atr_from_closes(c.closes, n=14)
    atr_c_pct = atr_c / c.current_price * 100
    move_c_pct = (c.current_price - c.prev_close) / c.prev_close * 100
    ratio_c = materiality_ratio(move_c_pct, atr_c_pct)
    print(f"  closes: {len(c.closes)}")
    print(f"  current: {c.current_price:.2f}  prev_close: {c.prev_close:.2f}")
    print(f"  ATR (14d, close-to-close): {atr_c:.2f}  ATR%: {atr_c_pct:.3f}%")
    print(f"  move: {move_c_pct:+.3f}%  ratio: {ratio_c:.2f}  material: {ratio_c > 1.5}")


if __name__ == "__main__":
    main()
