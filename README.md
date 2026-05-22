# Market Brief Agent

24/7 autonomous market monitor running on GitHub Actions. Alerts to phone via ntfy, logs to Notion.

See [SPEC.md](SPEC.md) for the full design.

## Jobs

- `price-monitor` — every 10 min, fires ATR-based material-move alerts
- `news-monitor` — every 10 min, Claude-filtered news on held tickers
- `scheduled-brief` — 07:00 / 13:00 / 22:30 CET, Claude-composed desk note

## Local dev

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in real values
```

## Deploy

Secrets needed in GitHub repo settings: `NOTION_TOKEN`, `FINNHUB_API_KEY`, `ANTHROPIC_API_KEY`, `NTFY_TOPIC`.
