"""Manual smoke test for ntfy push.

Usage:
    export NTFY_TOPIC=your-private-topic
    python -m scripts.smoke_ntfy
"""
from src.ntfy import push


def main() -> None:
    push(
        "Smoke test from market-brief. If you see this, the push pipeline works.",
        title="[TEST] market-brief",
        priority=3,
        tags=["white_check_mark"],
    )
    print("Pushed. Check your phone.")


if __name__ == "__main__":
    main()
