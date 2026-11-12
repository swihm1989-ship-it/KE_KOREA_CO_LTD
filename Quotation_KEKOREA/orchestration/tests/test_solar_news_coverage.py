"""Solar coverage, partial source failures, and empty-store recovery."""
import io
import unittest
from datetime import datetime,timedelta
from urllib.parse import unquote
from unittest.mock import patch,Mock
from Quotation_KEKOREA.orchestration.workflows import market_news as news

NOW=datetime(2026,11,12,10,0,tzinfo=news.KST)
STAMP='Wed, 11 Nov 2026 15:32:55 +0000'
def feed(title,url='https://example.com/solar'):
    return f'<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>{STAMP}</pubDate></item></channel></rss>'.encode()

class SolarCoverageTests(unittest.TestCase):
    def test_solar_combines_publisher_and_korean_and_english_sources(self):
        seen=[]
        def opener(req,timeout):
            url=unquote(req.full_url);seen.append(url)
            if 'pv-tech.org' in url:
                return io.BytesIO(feed('South Africa registers 2GW of new solar PV capacity in Q3 2026'))
            if 'US:en' in url:
                return io.BytesIO(feed('Hanwha Qcells reliability ratings','https://example.com/qcells'))
            return io.BytesIO(feed('태양광 및 BIPV 시장','https://example.com/bipv'))
        with patch.object(news,'urlopen',side_effect=opener):
            rows=news.fetch_category('태양광',NOW)
        self.assertEqual(len(rows),3)
        self.assertTrue(any('South Africa' in row['title'] and row['publisher']=='PV Tech' for row in rows))
        self.assertTrue(any('US:en' in url for url in seen))
        self.assertIn('태양광',news.CATEGORIES['태양광'])
        self.assertIn('BIPV',news.CATEGORIES['태양광'])

    def test_one_source_failure_does_not_hide_successful_solar_articles(self):
        def opener(req,timeout):
            if 'pv-tech.org' in req.full_url: return io.BytesIO(feed('Solar capacity growth'))
            raise OSError('source unavailable')
        with patch.object(news,'urlopen',side_effect=opener):
            rows=news.fetch_category('태양광',NOW)
        self.assertEqual(len(rows),1)

    def test_all_sources_failing_raises_instead_of_returning_empty_success(self):
        with patch.object(news,'urlopen',side_effect=OSError('offline')):
            with self.assertRaises(OSError): news.fetch_category('태양광',NOW)

    def test_duplicate_links_are_not_repeated_across_feeds(self):
        with patch.object(news,'urlopen',return_value=None) as opener:
            opener.side_effect=lambda *a,**kw: io.BytesIO(feed('Same solar news'))
            self.assertEqual(len(news.fetch_category('태양광',NOW)),1)

class EmptyNewsStoreTests(unittest.TestCase):
    def test_empty_database_falls_back_to_live_feed(self):
        from Quotation_KEKOREA.orchestration.ui import market_news_page as page
        store=Mock();store.fetch_category.return_value=[]
        row={'title':'Solar news','url':'https://example.com/solar',
             'published_at':datetime.now(news.KST).isoformat()}
        page._cached_news.clear()
        with patch.object(page.NewsSupabase,'from_config',return_value=store), patch.object(page,'fetch_category',return_value=[row]) as fetch, patch.object(page.Path,'exists',return_value=False):
            result,_=page._cached_news('태양광')
        self.assertEqual(result,[row])
        fetch.assert_called_once_with('태양광')
        page._cached_news.clear()

    def test_stale_collection_is_retained_if_live_refresh_fails(self):
        from Quotation_KEKOREA.orchestration.ui import market_news_page as page
        now=datetime.now(news.KST)
        row={'title':'Still recent solar news','url':'https://example.com/solar',
             'published_at':(now-timedelta(hours=3)).isoformat(),
             'collected_at':(now-timedelta(hours=2)).isoformat()}
        store=Mock();store.fetch_category.return_value=[row]
        page._cached_news.clear()
        with patch.object(page.st,'secrets',{}), patch.object(page.NewsSupabase,'from_config',return_value=store), patch.object(page,'fetch_category',side_effect=OSError('offline')), patch.object(page.Path,'exists',return_value=False):
            result,_=page._cached_news('태양광')
        self.assertEqual(result,[row])
        page._cached_news.clear()

    def test_empty_snapshot_does_not_suppress_live_feed(self):
        import json
        from Quotation_KEKOREA.orchestration.ui import market_news_page as page
        row={'title':'Live solar news','url':'https://example.com/live',
             'published_at':datetime.now(news.KST).isoformat()}
        snapshot=json.dumps({'updated_at':datetime.now(news.KST).isoformat(),'categories':{'태양광':[]}})
        page._cached_news.clear()
        with patch.object(page.st,'secrets',{}), patch.object(page.NewsSupabase,'from_config',return_value=None), patch.object(page,'fetch_category',return_value=[row]) as fetch, patch.object(page.Path,'exists',return_value=True), patch.object(page.Path,'read_text',return_value=snapshot):
            result,_=page._cached_news('태양광')
        self.assertEqual(result,[row])
        fetch.assert_called_once()
        page._cached_news.clear()

class DataCenterCoverageTests(unittest.TestCase):
    def test_data_center_includes_korean_and_english_company_news(self):
        seen=[]
        def opener(req,timeout):
            url=unquote(req.full_url);seen.append(url)
            title='엔비디아 경영진 관련 보도' if 'KR:ko' in url else 'New data center power investment'
            return io.BytesIO(feed(title,'https://example.com/'+str(len(seen))))
        with patch.object(news,'urlopen',side_effect=opener):
            rows=news.fetch_category('데이터센터',NOW)
        self.assertEqual(len(rows),2)
        self.assertIn('데이터센터',news.CATEGORIES['데이터센터'])
        self.assertTrue(any('NVIDIA' in u for u in seen))
        self.assertTrue(any('US:en' in u for u in seen))

    def test_ai_company_headlines_cannot_crowd_out_data_center_projects(self):
        def opener(req,timeout):
            if 'NVIDIA' in unquote(req.full_url):
                items=''.join(f'<item><title>Nvidia company story {i}</title><link>https://example.com/nv/{i}</link><pubDate>{STAMP}</pubDate></item>' for i in range(100))
                return io.BytesIO(('<rss><channel>'+items+'</channel></rss>').encode())
            return io.BytesIO(feed('New data center project','https://example.com/dc').replace(STAMP.encode(),b'Wed, 11 Nov 2026 14:32:55 +0000'))
        with patch.object(news,'urlopen',side_effect=opener):
            rows=news.fetch_category('데이터센터',NOW)
        self.assertTrue(any(row['title']=='New data center project' for row in rows))

class StoredDataCenterCoverageTests(unittest.TestCase):
    def test_stored_company_news_cannot_crowd_out_infrastructure(self):
        from Quotation_KEKOREA.orchestration.workflows.news_supabase import NewsSupabase
        now=datetime.now(news.KST)
        companies=[{'title':f'Nvidia company report {i}','url':f'https://example.com/nv/{i}',
                    'published_at':now.isoformat()} for i in range(100)]
        core={'title':'New data center construction','url':'https://example.com/dc',
              'published_at':(now-timedelta(hours=3)).isoformat()}
        def query(method,params): return [core] if 'or' in params else companies
        store=NewsSupabase('https://example.supabase.co','fake-key')
        with patch.object(NewsSupabase,'_request',side_effect=query):
            rows=store.fetch_category('데이터센터',now)
        self.assertEqual(len(rows),100)
        self.assertTrue(any(r['url']==core['url'] for r in rows))
