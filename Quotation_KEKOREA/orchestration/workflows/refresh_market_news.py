"""Refresh public market headline snapshot independently of Streamlit sessions."""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from Quotation_KEKOREA.orchestration.workflows.market_news import CATEGORIES, KST, fetch_category, retain_last_24_hours

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "market_news_snapshot.json"


def main() -> None:
    now = datetime.now(KST)
    previous = {}
    if SNAPSHOT.exists():
        try:
            previous = json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("categories", {})
        except (ValueError, OSError, AttributeError):
            previous = {}
    result = {}
    failures = []
    for category in CATEGORIES:
        try:
            result[category] = retain_last_24_hours(fetch_category(category, now=now), now)
        except (OSError, ValueError, TimeoutError) as exc:
            failures.append(f"{category}: {type(exc).__name__}")
            result[category] = retain_last_24_hours(previous.get(category, []), now)
    if len(failures) == len(CATEGORIES):
        raise RuntimeError("All feeds failed: " + ", ".join(failures))
    payload = {"updated_at": now.isoformat(), "categories": result,
               "errors": failures}
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    temp = SNAPSHOT.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, SNAPSHOT)
    print("Market news snapshot updated", now.isoformat(), "failures:", failures)


if __name__ == "__main__":
    main()
