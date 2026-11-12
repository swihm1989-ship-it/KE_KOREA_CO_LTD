"""News presentation: safe original links and compact category pagination."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from Quotation_KEKOREA.orchestration.ui import market_news_page as page


class NewsListTests(unittest.TestCase):
    def render(self, rows):
        render = getattr(page, 'news_list_html', None)
        self.assertTrue(callable(render), 'Compact news renderer must be available')
        return render(rows)

    def test_title_is_the_original_article_link(self):
        rendered = self.render([{'title': 'Solar deal - PV Tech', 'url': 'https://example.com/a?x=1&y=2',
                                 'publisher': 'PV Tech', 'published': '11-12 09:00'}])
        self.assertIn('Solar deal</a>', rendered)
        self.assertIn('https://example.com/a?x=1&amp;y=2', rendered)
        self.assertIn('PV Tech', rendered)
        self.assertIn('11-12 09:00 KST', rendered)
        self.assertNotIn('원문 보기', rendered)

    def test_external_text_is_escaped_and_unsafe_urls_are_not_links(self):
        rendered = self.render([{'title': '<script>alert(1)</script>', 'url': 'javascript:alert(1)',
                                 'publisher': '<img src=x onerror=alert(1)>',
                                 'summary': '<b>upstream excerpt</b>', 'image_url': 'data:text/html,evil'}])
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('href=', rendered)
        self.assertNotIn('<img ', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    def test_missing_media_has_no_fake_thumbnail_or_summary(self):
        rendered = self.render([{'title': 'Headline', 'url': 'https://example.com/a'}])
        self.assertNotIn('<img', rendered)
        self.assertNotIn('ke-news-summary', rendered)
        self.assertIn('Headline', rendered)



class NewsPageTests(unittest.TestCase):
    def app(self, provider):
        with patch.object(page, '_cached_news', side_effect=provider):
            app = AppTest.from_string('from Quotation_KEKOREA.orchestration.ui.market_news_page import render_market_news\nrender_market_news()', default_timeout=15).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_categories_are_tabs_and_pagination_keeps_all_stories(self):
        rows = [{'title': f'Headline {i}', 'url': f'https://example.com/{i}', 'publisher': 'Example', 'published': '11-12 09:00'} for i in range(7)]
        provider = lambda category: (rows, None)
        app = self.app(provider)
        self.assertEqual([t.label for t in app.tabs], list(page.CATEGORIES))
        rendered = '\n'.join(str(x.value) for x in app.markdown)
        self.assertIn('Headline 0', rendered)
        self.assertNotIn('Headline 5', rendered)
        with patch.object(page, '_cached_news', side_effect=provider):
            app.selectbox(key='market_page_태양광').set_value(2).run()
        self.assertFalse(app.exception)
        self.assertIn('Headline 5', '\n'.join(str(x.value) for x in app.markdown))
        self.assertEqual(len(app.get('link_button')), 0)

    def test_refresh_clamps_page_when_article_count_shrinks(self):
        rows = [{'title': f'Headline {i}', 'url': f'https://example.com/{i}'} for i in range(7)]
        provider = lambda category: (rows, None)
        app = self.app(provider)
        with patch.object(page, '_cached_news', side_effect=provider):
            app.selectbox(key='market_page_태양광').set_value(2).run()
        rows[:] = rows[:1]
        with patch.object(page, '_cached_news', side_effect=provider):
            app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.selectbox(key='market_page_태양광').value, 1)
        self.assertIn('Headline 0', '\n'.join(str(x.value) for x in app.markdown))

    def test_one_failed_category_does_not_hide_other_categories(self):
        def provider(category):
            if category == '태양광':
                raise OSError('offline')
            return [], None
        app = self.app(provider)
        self.assertEqual(len(app.warning), 1)
        self.assertEqual(len(app.info), 3)
