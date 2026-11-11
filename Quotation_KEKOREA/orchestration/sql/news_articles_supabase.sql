-- Run this migration ONLY in the new dedicated KE KOREA news project.
create table if not exists public.news_articles (
    id bigint generated always as identity primary key,
    category text not null check (category in ('태양광', '데이터센터', '원자재', '증시·거시경제')),
    title text not null,
    url text not null,
    publisher text not null default 'Unknown',
    published_at timestamptz not null,
    collected_at timestamptz not null default now(),
    unique (category, url)
);
create index if not exists news_articles_recent_idx
    on public.news_articles (category, published_at desc);
alter table public.news_articles enable row level security;
revoke all on public.news_articles from anon, authenticated;
-- No anon/authenticated policies: backend secret key only.
create extension if not exists pg_cron with schema pg_catalog;
select cron.schedule(
    'ke-korea-news-24h-cleanup',
    '*/30 * * * *',
    $$delete from public.news_articles where published_at < now() - interval '24 hours'$$
);
