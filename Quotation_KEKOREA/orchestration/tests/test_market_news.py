import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from Quotation_KEKOREA.orchestration.workflows.market_news import cutoff_kst, parse_rss

KST = ZoneInfo("Asia/Seoul")


class MarketNewsTests(unittest.TestCase):
    def test_cutoff_before_and_after_6pm(self):
        self.assertEqual(cutoff_kst(datetime(2026, 11, 11, 17, 0, tzinfo=KST)).day, 10)
        self.assertEqual(cutoff_kst(datetime(2026, 11, 11, 18, 0, tzinfo=KST)).day, 11)

    def test_pubdate_window_and_missing_fields(self):
        now = datetime(2026, 11, 11, 19, 0, tzinfo=KST)
        xml = b"""<rss><channel>
        <item><title>Recent</title><link>https://example.com/a</link><pubDate>Wed, 11 Nov 2026 09:30:00 GMT</pubDate></item>
        <item><title>Old</title><link>https://example.com/b</link><pubDate>Wed, 11 Nov 2026 08:30:00 GMT</pubDate></item>
        <item><title>Unsafe</title><link>javascript:alert(1)</link><pubDate>Wed, 11 Nov 2026 09:30:00 GMT</pubDate></item>
        </channel></rss>"""
        rows = parse_rss(xml, cutoff_kst(now), now)
        self.assertEqual([row["title"] for row in rows], ["Recent"])


if __name__ == "__main__":
    unittest.main()
