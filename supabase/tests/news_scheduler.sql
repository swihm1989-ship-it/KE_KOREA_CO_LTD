-- Read-only parser regression; no synthetic rows are stored.
do $$
declare n integer; result record;
begin
  select count(*) into n from news_scheduler.parse_rss(
  '<rss><channel>
  <item><title>Recent &amp; test</title><link>https://example.com/test</link><pubDate>Thu, 12 Nov 2026 05:00:00 GMT</pubDate></item>
  <item><title>Missing link</title><pubDate>Thu, 12 Nov 2026 05:00:00 GMT</pubDate></item>
  <item><title>Bad date</title><link>https://example.com/bad</link><pubDate>unknown</pubDate></item>
  <item><title>Unsafe</title><link>javascript:alert(1)</link><pubDate>Thu, 12 Nov 2026 05:00:00 GMT</pubDate></item>
  <item><title>Old</title><link>https://example.com/old</link><pubDate>Mon, 09 Nov 2026 05:00:00 GMT</pubDate></item>
  <item><title>Future</title><link>https://example.com/future</link><pubDate>Fri, 13 Nov 2026 05:00:00 GMT</pubDate></item>
  </channel></rss>', 'Test publisher','2026-11-12 06:00:00+00');
  assert n=1, 'RSS metadata/date/URL filtering failed';
  select * into result from news_scheduler.parse_rss('<rss><item><title>A &amp; B</title><link>https://example.com</link><pubDate>Thu, 12 Nov 2026 05:00:00 GMT</pubDate></item></rss>','Fallback','2026-11-12 06:00:00+00');
  assert result.title='A & B' and result.publisher='Fallback','Publisher/entity regression';
  begin
    perform * from news_scheduler.parse_rss('<!DOCTYPE rss><rss/>','Fallback',now());
    raise exception using errcode='P0002',message='DTD must be rejected';
  exception when raise_exception then null;
  end;
end $$;
