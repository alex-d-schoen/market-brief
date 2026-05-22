"""Anthropic Claude client + prompts for the three composers.

Spec-driven prompts:
  - price alert: 3 lines max
  - news filter: JSON {material, thesis_impact, alert_text}
  - scheduled brief: plain text, ~350 words, desk-note tone
"""
from __future__ import annotations

import json
from typing import Any

import anthropic

from .config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    MAX_TOKENS_ALERT,
    MAX_TOKENS_BRIEF,
)


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ============================ price alert ============================

_PRICE_ALERT_SYSTEM = """You compose terse market-move alerts for a phone push notification.

Hard rules:
- Exactly 3 lines (or 2 if no position thesis is provided).
- Line 1: TICKER + emoji (UP → 📈, DOWN → 📉) + signed move % + "ATR" + ratio. Format: "AAPL 📈 +2.4% ATR 1.7x"
- Line 2: One short clause naming the most likely driver. If unclear, write exactly "driver unclear" — NEVER guess.
- Line 3 (only if a thesis is provided): "Thesis: CONFIRMS|THREATENS|NEUTRAL" + 5-word reason.
- No preamble, no markdown, no quotes around the output."""


def compose_price_alert(
    *,
    ticker: str,
    move_pct: float,
    atr_ratio: float,
    asset_class: str,
    is_position: bool,
    thesis: str | None = None,
) -> str:
    """Return the ~3-line alert string ready for ntfy."""
    direction = "UP" if move_pct >= 0 else "DOWN"
    parts = [
        f"Ticker: {ticker} ({asset_class})",
        f"Move: {move_pct:+.2f}% (direction: {direction})",
        f"ATR ratio: {atr_ratio:.2f}x typical daily range",
        f"Held position: {'yes' if is_position else 'no (watchlist)'}",
    ]
    if is_position and thesis:
        parts.append(f"Position thesis: {thesis}")

    user = "\n".join(parts) + "\n\nCompose the alert per the rules."

    resp = _client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS_ALERT,
        system=_PRICE_ALERT_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    return _first_text(resp).strip()


# ============================ news filter ============================

_NEWS_FILTER_SYSTEM = """You filter financial news for an investor monitoring specific positions.

Decide if the headline is MATERIAL — meaning it could plausibly move the stock 1%+ OR meaningfully changes the investment case.

Material examples: earnings beats/misses, M&A, guidance changes, major contracts, regulatory action, executive changes at the CEO/CFO level, large litigation, product launches with revenue impact.

Not material: routine analyst rating changes, generic sector commentary, technical-only chatter, opinion pieces with no new facts.

Return a 3-line alert_text in the same style as price alerts:
- Line 1: TICKER + 📰 + 6-10 word headline distillation
- Line 2: One short clause on the likely impact
- Line 3 (only if thesis provided AND material): "Thesis: CONFIRMS|THREATENS|NEUTRAL" + 5-word reason

For non-material items, alert_text can be a single short line summarizing why it was filtered."""


_NEWS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "material": {"type": "boolean"},
        "thesis_impact": {
            "type": "string",
            "enum": ["CONFIRMS", "THREATENS", "NEUTRAL", "N/A"],
        },
        "alert_text": {"type": "string"},
    },
    "required": ["material", "thesis_impact", "alert_text"],
    "additionalProperties": False,
}


def filter_news(
    *,
    ticker: str,
    asset_class: str,
    headline: str,
    summary: str,
    is_position: bool,
    thesis: str | None = None,
) -> dict[str, Any]:
    """Returns {material: bool, thesis_impact: str, alert_text: str}."""
    parts = [
        f"Ticker: {ticker} ({asset_class})",
        f"Held position: {'yes' if is_position else 'no (watchlist)'}",
    ]
    if is_position and thesis:
        parts.append(f"Position thesis: {thesis}")
    parts.append(f"Headline: {headline}")
    if summary:
        parts.append(f"Summary: {summary[:1500]}")

    user = "\n".join(parts) + "\n\nReturn the JSON object."

    resp = _client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS_ALERT,
        system=_NEWS_FILTER_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": _NEWS_SCHEMA}},
        messages=[{"role": "user", "content": user}],
    )
    text = _first_text(resp)
    return json.loads(text)


# ============================ scheduled brief ============================

_BRIEF_SYSTEM = """You write desk-note morning/midday/evening market briefs for an individual investor.

Rules:
- Plain text only. NO markdown headers, NO asterisks, NO bullet character salads — ntfy renders plain. Use UPPERCASE section labels on their own line.
- Sections in this exact order: POSITIONS / WATCHLIST MOVERS / EARNINGS TODAY / MARKET PULSE / WATCH FOR.
- Under 350 words total.
- Tone: trading desk note — terse, factual, no hedge language ("investors should consider", "it remains to be seen"). State what's happening and what to watch.
- If a section has nothing to say, write "(quiet)" on one line under the label and move on. Do not invent activity.
- End with a single-line WATCH FOR with 1–3 specific things to track today/this session."""


def compose_brief(
    *,
    time_label: str,  # "Morning Brief" / "Midday Brief" / "Evening Brief"
    positions_block: str,
    watchlist_block: str,
    earnings_block: str,
    market_pulse_block: str,
) -> str:
    """Return the ~350-word brief text ready for ntfy."""
    user = (
        f"Slot: {time_label} (Europe/Zurich)\n\n"
        f"=== POSITIONS DATA ===\n{positions_block or '(none)'}\n\n"
        f"=== WATCHLIST DATA ===\n{watchlist_block or '(none)'}\n\n"
        f"=== EARNINGS TODAY ===\n{earnings_block or '(none)'}\n\n"
        f"=== MARKET HEADLINES ===\n{market_pulse_block or '(none)'}\n\n"
        "Compose the brief per the rules."
    )
    resp = _client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS_BRIEF,
        system=_BRIEF_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    return _first_text(resp).strip()


# ============================ helpers ============================

def _first_text(resp: anthropic.types.Message) -> str:
    for block in resp.content:
        if block.type == "text":
            return block.text
    return ""
