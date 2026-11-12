-- Fetch public RSS metadata within Supabase, independent of GitHub/Streamlit.
create extension if not exists pg_net;
create schema if not exists news_scheduler;
revoke all on schema news_scheduler from public, anon, authenticated;
create table if not exists news_scheduler.sources (
  id text primary key, category text not null,
  url text not null check (url like 'https://news.google.com/rss/search?%' or url='https://www.pv-tech.org/feed/'),
  publisher text not null
);
create table if not exists news_scheduler.requests (
  id bigint primary key, source_id text references news_scheduler.sources(id),
  requested_at timestamptz not null default now(), finished_at timestamptz,
  status text not null default 'pending', articles integer, http_status integer, error_code text
);
alter table news_scheduler.sources enable row level security;
alter table news_scheduler.requests enable row level security;
revoke all on all tables in schema news_scheduler from public, anon, authenticated;

create or replace function news_scheduler.parse_rss(body text, fallback_publisher text, as_of timestamptz)
returns table(title text,url text,publisher text,published_at timestamptz)
language plpgsql set search_path = pg_catalog as $$
declare item record; stamp timestamptz;
begin
  if length(body)>1000000 or body ~* '<!DOCTYPE|<!ENTITY' then
    raise exception 'RSS exceeds size limit or declares entities';
  end if;
  for item in select x.* from xmltable('//item' passing xmlparse(document body)
      columns headline text path 'title', link text path 'link', source text path 'source', pubdate text path 'pubDate') x loop
    if nullif(btrim(item.headline),'') is null or coalesce(item.link,'') not like 'https://%' or item.pubdate is null then continue; end if;
    begin stamp := item.pubdate::timestamptz;
    exception when invalid_datetime_format or datetime_field_overflow then continue; end;
    if stamp < as_of - interval '24 hours' or stamp > as_of then continue; end if;
    title := left(btrim(item.headline),240); url := btrim(item.link);
    publisher := coalesce(nullif(btrim(item.source),''),fallback_publisher); published_at := stamp;
    return next;
  end loop;
end $$;

create or replace function news_scheduler.enqueue()
returns integer language plpgsql set search_path = pg_catalog as $$
declare s record; request_id bigint; queued integer := 0;
begin
  if not pg_try_advisory_xact_lock(61412037) then return 0; end if;
  for s in select * from news_scheduler.sources loop
    if exists(select 1 from news_scheduler.requests r where r.source_id=s.id and r.requested_at>now()-interval '20 minutes') then continue; end if;
    request_id := net.http_get(url:=s.url, headers:='{"User-Agent":"KEKOREA-MarketDashboard/1.0"}'::jsonb,timeout_milliseconds:=12000);
    insert into news_scheduler.requests(id,source_id) values(request_id,s.id);
    queued := queued+1;
  end loop;
  return queued;
end $$;

create or replace function news_scheduler.ingest()
returns integer language plpgsql set search_path = pg_catalog as $$
declare r record; written integer; total integer := 0;
begin
  if not pg_try_advisory_xact_lock(61412038) then return 0; end if;
  for r in select q.id,q.requested_at,s.category,s.publisher,h.status_code,h.content,h.error_msg,h.timed_out
      from news_scheduler.requests q join news_scheduler.sources s on s.id=q.source_id
      left join net._http_response h on h.id=q.id
      where q.status='pending' and (h.id is not null or q.requested_at<now()-interval '15 minutes') loop
    begin
      if r.status_code is distinct from 200 or coalesce(r.timed_out,false) or r.error_msg is not null then
        update news_scheduler.requests set status='failed',finished_at=now(),http_status=r.status_code,error_code='http_or_timeout' where id=r.id;
        continue;
      end if;
      insert into public.news_articles(category,title,url,publisher,published_at,collected_at)
        select distinct on (p.url) r.category,p.title,p.url,p.publisher,p.published_at,now()
        from news_scheduler.parse_rss(r.content,r.publisher,now()) p order by p.url,p.published_at desc
        on conflict (category,url) do update set title=excluded.title,publisher=excluded.publisher,published_at=excluded.published_at,collected_at=excluded.collected_at;
      get diagnostics written = row_count;
      update news_scheduler.requests set status=case when written>0 then 'success' else 'empty' end,
        articles=written,finished_at=now(),http_status=200 where id=r.id;
      total := total+written;
    exception when others then
      update news_scheduler.requests set status='failed',finished_at=now(),http_status=r.status_code,error_code=SQLSTATE where id=r.id;
    end;
  end loop;
  delete from news_scheduler.requests where requested_at < now()-interval '7 days';
  return total;
end $$;
revoke all on all functions in schema news_scheduler from public,anon,authenticated;
insert into news_scheduler.sources(id,category,url,publisher) values('category-0-source-0','태양광','https://news.google.com/rss/search?q=%28%22solar+power%22+OR+%22solar+energy%22+OR+%22solar+PV%22+OR+photovoltaics+OR+polysilicon+OR+%22solar+wafer%22+OR+%22solar+cell%22+OR+%22solar+module%22+OR+%ED%83%9C%EC%96%91%EA%B4%91+OR+BIPV+OR+Qcells+OR+%ED%95%9C%ED%99%94%ED%81%90%EC%85%80%29+when%3A2d&hl=ko&gl=KR&ceid=KR%3Ako','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-0-source-1','태양광','https://news.google.com/rss/search?q=%28%22solar+power%22+OR+%22solar+energy%22+OR+%22solar+PV%22+OR+photovoltaics+OR+polysilicon+OR+%22solar+wafer%22+OR+%22solar+cell%22+OR+%22solar+module%22+OR+%ED%83%9C%EC%96%91%EA%B4%91+OR+BIPV+OR+Qcells+OR+%ED%95%9C%ED%99%94%ED%81%90%EC%85%80%29+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-0-source-2','태양광','https://www.pv-tech.org/feed/','PV Tech') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-1-source-0','데이터센터','https://news.google.com/rss/search?q=%28%22data+center%22+OR+%22data+centre%22+OR+datacenter+OR+%EB%8D%B0%EC%9D%B4%ED%84%B0%EC%84%BC%ED%84%B0+OR+%22AI+infrastructure%22+OR+%22AI+%EC%9D%B8%ED%94%84%EB%9D%BC%22%29+when%3A2d&hl=ko&gl=KR&ceid=KR%3Ako','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-1-source-1','데이터센터','https://news.google.com/rss/search?q=%28%22data+center%22+OR+%22data+centre%22+OR+datacenter+OR+%EB%8D%B0%EC%9D%B4%ED%84%B0%EC%84%BC%ED%84%B0+OR+%22AI+infrastructure%22+OR+%22AI+%EC%9D%B8%ED%94%84%EB%9D%BC%22%29+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-1-source-2','데이터센터','https://news.google.com/rss/search?q=%28NVIDIA+OR+%EC%97%94%EB%B9%84%EB%94%94%EC%95%84+OR+%22Jensen+Huang%22+OR+%22%EC%A0%A0%EC%8A%A8+%ED%99%A9%22+OR+%EC%A0%A0%EC%8A%A8%ED%99%A9%29+when%3A2d&hl=ko&gl=KR&ceid=KR%3Ako','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-1-source-3','데이터센터','https://news.google.com/rss/search?q=%28NVIDIA+OR+%EC%97%94%EB%B9%84%EB%94%94%EC%95%84+OR+%22Jensen+Huang%22+OR+%22%EC%A0%A0%EC%8A%A8+%ED%99%A9%22+OR+%EC%A0%A0%EC%8A%A8%ED%99%A9%29+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-2-source-0','원자재','https://news.google.com/rss/search?q=%28%22crude+oil%22+OR+%22natural+gas%22+OR+copper+OR+LNG+OR+%EC%9B%90%EC%9C%A0+OR+%EA%B5%AD%EC%A0%9C%EC%9C%A0%EA%B0%80+OR+%EC%B2%9C%EC%97%B0%EA%B0%80%EC%8A%A4+OR+%EA%B5%AC%EB%A6%AC+OR+%EC%9B%90%EC%9E%90%EC%9E%AC%29+when%3A2d&hl=ko&gl=KR&ceid=KR%3Ako','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-2-source-1','원자재','https://news.google.com/rss/search?q=%28%22crude+oil%22+OR+%22natural+gas%22+OR+copper+OR+LNG+OR+%EC%9B%90%EC%9C%A0+OR+%EA%B5%AD%EC%A0%9C%EC%9C%A0%EA%B0%80+OR+%EC%B2%9C%EC%97%B0%EA%B0%80%EC%8A%A4+OR+%EA%B5%AC%EB%A6%AC+OR+%EC%9B%90%EC%9E%90%EC%9E%AC%29+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-3-source-0','증시·거시경제','https://news.google.com/rss/search?q=%28%22stock+market%22+OR+KOSPI+OR+Nasdaq+OR+%22Federal+Reserve%22+OR+inflation+OR+%EC%BD%94%EC%8A%A4%ED%94%BC+OR+%EC%BD%94%EC%8A%A4%EB%8B%A5+OR+%EC%A6%9D%EC%8B%9C+OR+%EA%B8%B0%EC%A4%80%EA%B8%88%EB%A6%AC+OR+%ED%99%98%EC%9C%A8+OR+%EA%B1%B0%EC%8B%9C%EA%B2%BD%EC%A0%9C%29+when%3A2d&hl=ko&gl=KR&ceid=KR%3Ako','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
insert into news_scheduler.sources(id,category,url,publisher) values('category-3-source-1','증시·거시경제','https://news.google.com/rss/search?q=%28%22stock+market%22+OR+KOSPI+OR+Nasdaq+OR+%22Federal+Reserve%22+OR+inflation+OR+%EC%BD%94%EC%8A%A4%ED%94%BC+OR+%EC%BD%94%EC%8A%A4%EB%8B%A5+OR+%EC%A6%9D%EC%8B%9C+OR+%EA%B8%B0%EC%A4%80%EA%B8%88%EB%A6%AC+OR+%ED%99%98%EC%9C%A8+OR+%EA%B1%B0%EC%8B%9C%EA%B2%BD%EC%A0%9C%29+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen','Google News') on conflict(id) do update set category=excluded.category,url=excluded.url,publisher=excluded.publisher;
select cron.schedule('ke-korea-news-fetch','7,37 * * * *','select news_scheduler.enqueue();');
select cron.schedule('ke-korea-news-ingest','* * * * *','select news_scheduler.ingest();');
