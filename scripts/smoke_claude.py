"""Manual smoke test for Claude composers.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python -m scripts.smoke_claude
"""
from src.claude import compose_price_alert, filter_news, compose_brief


def main() -> None:
    print("=== price alert (AAPL, held position) ===")
    msg = compose_price_alert(
        ticker="AAPL",
        move_pct=2.4,
        atr_ratio=1.7,
        asset_class="Stock",
        is_position=True,
        thesis="Services revenue + buybacks support 25x multiple",
    )
    print(msg)

    print("\n=== news filter (NVDA earnings beat, watchlist) ===")
    result = filter_news(
        ticker="NVDA",
        asset_class="Stock",
        headline="Nvidia Q4 revenue beats by 8%, raises Q1 guide",
        summary="Nvidia reported Q4 revenue of $39.3B vs $36.4B est, citing data center demand. Q1 guide of $43B vs $42B est.",
        is_position=False,
    )
    print(result)

    print("\n=== news filter (routine analyst note, not material) ===")
    result = filter_news(
        ticker="AAPL",
        asset_class="Stock",
        headline="Wedbush reiterates Outperform on Apple, raises PT to $325",
        summary="Wedbush analyst Dan Ives reiterated his Outperform rating and bumped his price target.",
        is_position=True,
        thesis="Services revenue + buybacks support 25x multiple",
    )
    print(result)

    print("\n=== morning brief (small) ===")
    brief = compose_brief(
        time_label="Morning Brief",
        positions_block="AAPL: +1.6% to 310.93 (ATR ratio 0.86)\nbitcoin: -1.2% to 76609 (ATR ratio 1.04)",
        watchlist_block="NVDA: flat\nUBSG.SW: -0.3%",
        earnings_block="(none today)",
        market_pulse_block="S&P futures +0.3%. 10y yield 4.32% (-2bps). Brent 78.40 +0.5%.",
    )
    print(brief)


if __name__ == "__main__":
    main()
