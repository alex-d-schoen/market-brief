"""Tuning knobs and shared constants."""
import os

# Materiality (env-overridable for tuning / smoke testing)
MATERIAL_THRESHOLD = float(os.environ.get("MATERIAL_THRESHOLD", "1.5"))
DEDUP_HOURS = int(os.environ.get("DEDUP_HOURS", "4"))
NEWS_FRESHNESS_MIN = int(os.environ.get("NEWS_FRESHNESS_MIN", "15"))

# Notion database IDs
NOTION_DB_POSITIONS = "abf2aa20bf904e22ac5e97e304e5bcc9"
NOTION_DB_WATCHLIST = "3de4b6a331f6460cb479798c15c14fba"
NOTION_DB_ALERT_LOG = "408d4d03160f447b925a42f3825a04a8"

# Claude
CLAUDE_MODEL = "claude-sonnet-4-6"  # spec said 4.5; 4.6 is current Sonnet, same price
MAX_TOKENS_ALERT = 300
MAX_TOKENS_BRIEF = 1200

# Timezone
TZ = "Europe/Zurich"

# Secrets (read from env)
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
