# Market Brief Agent — Project Spec for Claude Code

> This is the kickoff prompt for Claude Code. Save it locally, open Claude Code in an empty project directory, and paste this file's contents as your first message. Claude Code will read it, ask any clarifying questions, then build the project.

---

## Project goal

Build a **24/7 autonomous market-monitoring agent** that runs on GitHub Actions (free), pushes alerts to my phone via ntfy, and logs everything to Notion. I'm a Swiss finance student (HSG) tracking my own positions and watchlist. The agent should be vibe-coded — I'll talk to you, you write the code, I push to GitHub.

## Architecture

**Runtime:** GitHub Actions (free tier, cron-scheduled jobs)
**Language:** Python (preferred — simpler for cron/data work; switch to TypeScript only if you have strong reason)
**Hosting cost:** $0 forever (GitHub Actions free tier is plenty)
**Ongoing API cost:** ~$2-5/mo Anthropic only

**Three scheduled jobs** (three separate `.github/workflows/*.yml` files):

1. **`price-monitor.yml`** — every 10 min, 24/7
   - Polls all `Open` positions + `Active` watchlist from Notion
   - Fetches current price + 14-day OHLC from Finnhub (stocks) / CoinGecko (crypto)
   - Computes ATR (Average True Range) per asset
   - Fires ntfy alert if today's move > 1.5× the asset's typical daily range
   - Dedup: skip if same ticker alerted in last 4h (check Notion Alert Log)
   - Logs every alert to Notion Alert Log

2. **`news-monitor.yml`** — every 10 min, 24/7
   - For each stock ticker, pulls Yahoo Finance per-ticker RSS (`https://feeds.finance.yahoo.com/rss/2.0/headline?s=TICKER`)
   - Filters to items published in last 15 min
   - Dedup by URL against Notion Alert Log
   - For each new item: send to Claude (Anthropic API) with the position's thesis, ask if material + thesis impact
   - If material → ntfy push with article link, log to Notion
   - If not material → still log to Notion (filtered, no push)

3. **`scheduled-brief.yml`** — 07:00, 13:00, 22:30 CET (3 cron triggers in one file)
   - Pulls positions + watchlist + earnings calendar + market RSS (WSJ, MarketWatch)
   - Sends full context to Claude → composes ~350-word structured brief
   - Push to ntfy + log to Notion
   - Timezone: Europe/Zurich

## Notion data sources (already created, ready to use)

Three databases under a parent page called "Market Brief Agent":

| Database | Database ID | Filter |
|---|---|---|
| Positions | `abf2aa20bf904e22ac5e97e304e5bcc9` | `Status = Open` |
| Watchlist | `3de4b6a331f6460cb479798c15c14fba` | `Status = Active` |
| Alert Log | `408d4d03160f447b925a42f3825a04a8` | (write target + dedup source) |

**Positions schema:** Ticker (title), Asset Class (Stock/ETF/Crypto), Quantity (num), Entry Price (num), Entry Date (date), Currency (CHF/USD/EUR), Thesis (text), Stop Loss (num), Target Price (num), Sector Tags (multi-select), Status (Open/Closed)

**Watchlist schema:** Ticker (title), Asset Class, Currency, Why Watching (text), Sector Tags, Status (Active/Paused)

**Alert Log schema:** Title (title), Timestamp (date+datetime), Type (Price Alert / News Alert / Morning Brief / Midday Brief / Evening Brief), Ticker (text), Message (text), Source URL (url), Move % (num), ATR Ratio (num)

The Notion integration secret needs to be set up by me — I'll create one at notion.so/my-integrations called "GitHub Actions Market Brief", share each of the 3 databases with it, and pass the secret as a GitHub Actions secret named `NOTION_TOKEN`.

## Credentials (as GitHub Actions secrets)

I'll add these in the GitHub repo settings — your code should read them from environment variables:

| Secret name | What it is |
|---|---|
| `NOTION_TOKEN` | Notion integration secret (starts with `ntn_`) |
| `FINNHUB_API_KEY` | Finnhub stock data |
| `ANTHROPIC_API_KEY` | Claude API for synthesis |
| `NTFY_TOPIC` | My private ntfy topic name (random string) |

CoinGecko free tier doesn't need a key.

## ntfy push design

POST to `https://ntfy.sh/<NTFY_TOPIC>` with body = message text and headers:
- `Title`: short title
- `Priority`: 4 for alerts (loud), 3 for scheduled briefs (normal)
- `Tags`: emoji shortcode (`chart_with_upwards_trend`, `chart_with_downwards_trend`, `newspaper`, `sunrise`, `sun_with_face`, `crescent_moon`)
- `Click` (news only): URL to open on tap

## Materiality logic (price monitor)

```
For each asset:
  fetch 15 daily closes (or OHLC for stocks)
  compute True Range per day: max(high-low, |high-prev_close|, |low-prev_close|)
  ATR = mean of last 14 TRs
  current_move_pct = (current_price - today_open) / today_open * 100
  atr_pct = ATR / current_price * 100
  ratio = |current_move_pct| / atr_pct
  if ratio > 1.5: ALERT (material move)
```

For crypto (no intraday OHLC on free CoinGecko): use yesterday's close as "today open" proxy. Document this approximation.

## Claude synthesis prompts (high-level)

**Price alert composer:**
> 3 lines max. Line 1: TICKER + 📈/📉 emoji + move% + ATR ratio. Line 2: most likely driver (one short clause, say "driver unclear" if you don't know — never guess). Line 3 (only if held position with thesis): "Thesis: CONFIRMS/THREATENS/NEUTRAL" + 5-word reason.

**News filter + composer:**
> Return JSON: `{material: bool, thesis_impact: CONFIRMS|THREATENS|NEUTRAL|N/A, alert_text: <3-line message>}`. Material = could move price 1%+ OR meaningfully changes investment case. Routine analyst upgrades = not material. Earnings/M&A/guidance/regulatory/major contracts = material.

**Scheduled brief composer:**
> Plain text (no markdown headers — ntfy renders as plain). Sections: POSITIONS / WATCHLIST MOVERS / EARNINGS TODAY / MARKET PULSE / WATCH FOR. Under 350 words. Tone: desk-note terse, no fluff, no "investors should consider" hedge language.

Use Claude Sonnet 4.5 (`claude-sonnet-4-5`) for all three. Max tokens: 300 for alerts, 1200 for full brief.

## Suggested file layout

```
.
├── .github/
│   └── workflows/
│       ├── price-monitor.yml
│       ├── news-monitor.yml
│       └── scheduled-brief.yml
├── src/
│   ├── __init__.py
│   ├── notion_client.py       # wrappers around Notion API
│   ├── market_data.py         # Finnhub + CoinGecko fetchers
│   ├── news.py                # Yahoo + WSJ + MarketWatch RSS parsers
│   ├── ntfy.py                # push notification sender
│   ├── claude.py              # Anthropic API client + prompts
│   ├── atr.py                 # ATR computation
│   ├── price_monitor.py       # entrypoint for job 1
│   ├── news_monitor.py        # entrypoint for job 2
│   └── scheduled_brief.py     # entrypoint for job 3
├── requirements.txt
├── README.md
└── .gitignore
```

## Tuning knobs (must be easy to change later)

- `MATERIAL_THRESHOLD` (default 1.5) — ATR multiplier
- `DEDUP_HOURS` (default 4) — don't re-alert same ticker within X hours
- `NEWS_FRESHNESS_MIN` (default 15) — only consider news items < X min old

Put these in a `config.py` or as constants at the top of each entrypoint.

## How I want to work with you

1. **Don't ask me to write code.** I'll never touch a `.py` file. You write, I run / commit / push.
2. **Be terse.** I'm comfortable with technical concepts. Skip explanations of basics unless I ask.
3. **Iterate visibly.** When you make a change, tell me what changed and why in 1-2 lines, not paragraphs.
4. **Plain text in chat is fine** — no need for heavy formatting in your responses.
5. I'm in Europe/Zurich timezone. The current date is May 2026.

## Build order (your suggested plan, confirm or override)

1. Initialize repo + `.gitignore` + `requirements.txt`
2. Implement `notion_client.py` (read positions/watchlist, write alert log) — test with a manual script
3. Implement `market_data.py` + `atr.py` — verify ATR math on a known ticker
4. Implement `ntfy.py` — verify a push lands on my phone
5. Implement `claude.py` + price alert prompt
6. Wire up `price_monitor.py` end-to-end, test locally with one ticker
7. Add `news.py` + `news_monitor.py`
8. Add `scheduled_brief.py`
9. Write the three `.github/workflows/*.yml` files with cron triggers
10. Push, set secrets in GitHub repo settings, enable Actions, watch first run

## First message to me

Read this spec. Confirm the architecture makes sense to you. If yes, ask me three things:
1. Do I have a GitHub account ready (and the `gh` CLI installed)?
2. What should the repo be called?
3. Should we proceed with Python or do I prefer TypeScript?

Then we start with step 1.

---

## Appendix — context I've already validated

- ntfy app installed on my phone, topic subscribed, test message received
- Finnhub API key in hand
- Anthropic API key in hand, $5 in credits loaded
- Notion: 3 databases created (IDs above), 2 example positions seeded (AAPL, bitcoin), 2 watchlist (NVDA, UBSG.SW)
- I still need to: create the Notion integration + share it with the 3 databases (~2 min, will do before first GitHub Actions run)

Previous attempt was building this in n8n. We're scrapping it — n8n Cloud signup failed in my region and self-hosting requires always-on hardware I don't have. GitHub Actions runs on GitHub's infra so my laptop can sleep.
