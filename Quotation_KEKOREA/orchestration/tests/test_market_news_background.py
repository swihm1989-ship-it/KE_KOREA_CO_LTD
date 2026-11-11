import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from tempfile import TemporaryDirectory
import json

from Quotation_KEKOREA.orchestration.workflows import refresh_market_news as job


class BackgroundNewsTests(unittest.TestCase):
    def test_snapshot_written_without_streamlit_session(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "market_news_snapshot.json"
            with patch.object(job, "SNAPSHOT", target), patch.object(
                job, "fetch_category", return_value=[
                    {"title": "Solar news", "url": "https://example.com/news",
                     "publisher": "Example", "published": "11-11 19:00"}
                ]
            ):
                job.main()
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(set(data["categories"]), set(job.CATEGORIES))
            self.assertEqual(data["categories"]["태양광"][0]["title"], "Solar news")

    def test_all_sources_failing_does_not_overwrite(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "market_news_snapshot.json"
            target.write_text('{"categories":{}}', encoding="utf-8")
            with patch.object(job, "SNAPSHOT", target), patch.object(
                job, "fetch_category", side_effect=OSError("offline")
            ):
                with self.assertRaises(RuntimeError):
                    job.main()
            self.assertEqual(target.read_text(encoding="utf-8"), '{"categories":{}}')


if __name__ == "__main__":
    unittest.main()
