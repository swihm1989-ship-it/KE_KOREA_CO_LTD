"""Unit tests for private Supabase REST news storage (no network)."""
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo
from Quotation_KEKOREA.orchestration.workflows.news_supabase import NewsSupabase


class NewsSupabaseTests(unittest.TestCase):
    def test_unconfigured_is_disabled(self):
        self.assertIsNone(NewsSupabase.from_config({}))
        with self.assertRaises(ValueError):
            NewsSupabase.from_config({"NEWS_SUPABASE_URL": "http://localhost",
                                      "NEWS_SUPABASE_SECRET_KEY": "secret"})

    def test_upsert_excludes_expired(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        store = NewsSupabase("https://example.supabase.co", "fake-secret")
        old = (now - timedelta(hours=25)).isoformat()
        new = (now - timedelta(minutes=10)).isoformat()
        with patch.object(NewsSupabase, "_request", return_value=None) as request:
            count = store.upsert_categories({"태양광": [
                {"url": "https://example.com/old", "title": "old", "published_at": old},
                {"url": "https://example.com/new", "title": "new", "published_at": new}
            ]}, now=now)
        self.assertEqual(count, 1)
        self.assertEqual(request.call_args.args[2][0]["url"], "https://example.com/new")

    def test_read_filters_expired_even_if_database_returns_it(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        store = NewsSupabase("https://example.supabase.co", "fake-secret")
        with patch.object(NewsSupabase, "_request", return_value=[
            {"title": "expired", "url": "https://example.com/old", "publisher": "X",
             "published_at": (now - timedelta(hours=25)).isoformat()},
            {"title": "fresh", "url": "https://example.com/new", "publisher": "X",
             "published_at": (now - timedelta(minutes=2)).isoformat()},
        ]):
            result = store.fetch_category("태양광", now=now)
        self.assertEqual([r["title"] for r in result], ["fresh"])


if __name__ == "__main__":
    unittest.main()
