"""Write a test row to the Alert Log to verify write permissions.

Usage:
    export NOTION_TOKEN=ntn_xxx
    python -m scripts.smoke_notion_write
"""
from src.notion_client import log_alert


def main() -> None:
    log_alert(
        title="[TEST] smoke write",
        alert_type="Price Alert",
        ticker="TEST",
        message="smoke test row from scripts/smoke_notion_write.py — safe to delete",
        move_pct=0.0,
        atr_ratio=0.0,
    )
    print("Wrote one test row to Alert Log. Check Notion and delete it.")


if __name__ == "__main__":
    main()
