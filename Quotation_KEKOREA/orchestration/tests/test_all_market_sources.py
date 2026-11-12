import io
import unittest
from datetime import datetime
from unittest.mock import patch
from urllib.parse import unquote
from Quotation_KEKOREA.orchestration.workflows import market_news as news

class AllMarketSourcesTests(unittest.TestCase):
    def test_materials_and_macro_have_korean_terms_and_both_editions(self):
        now = datetime.now(news.KST)
        from email.utils import format_datetime
        xml = ('<rss><channel><item><title>Headline</title><link>https://example.com/a</link><pubDate>'
               + format_datetime(now) + '</pubDate></item></channel></rss>').encode()
        for category, keyword in [('원자재', '구리'), ('증시·거시경제', '코스피')]:
            with self.subTest(category=category):
                seen = []
                def open_feed(request, timeout):
                    seen.append(unquote(request.full_url))
                    return io.BytesIO(xml)
                with patch.object(news, 'urlopen', side_effect=open_feed):
                    news.fetch_category(category, now)
                self.assertIn(keyword, news.CATEGORIES[category])
                self.assertTrue(any('KR:ko' in u for u in seen))
                self.assertTrue(any('US:en' in u for u in seen))
