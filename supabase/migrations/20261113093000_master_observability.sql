-- Isolated operational metadata only. No audit log or business-table changes.
create table public.kekorea_telemetry_events (
  event_id uuid primary key,
  run_id uuid not null,
  span_id uuid not null,
  parent_span_id uuid,
  event_type text not null check (event_type in ('start','finish')),
  task text not null check (task in ('mail.collect','ai.request','contract.analyze','contract.generate','trade.extract','document.generate','monitor.health','other')),
  document_kind text check (document_kind in ('PI','PO','CI','PL','CONTRACT')),
  status text not null check (status in ('running','success','failure')),
  started_at timestamptz not null,
  ended_at timestamptz,
  duration_ms double precision check (duration_ms >= 0 and duration_ms < 'Infinity'::float8),
  model text check (model = 'other' or model ~ '^(gpt-([0-9](\.[0-9])?(-(mini|nano|pro|sol|terra|luna|astra|codex))?|4o(-mini)?)|o[134](-mini)?)(-[0-9]{4}-[0-9]{2}-[0-9]{2})?$'),
  input_tokens bigint check (input_tokens between 0 and 1000000000),
  output_tokens bigint check (output_tokens between 0 and 1000000000),
  cached_input_tokens bigint check (cached_input_tokens between 0 and 1000000000),
  estimated_cost_usd numeric(24,12) check (estimated_cost_usd >= 0),
  pricing_status text check (pricing_status in ('estimated','missing_usage','unknown_model','unsupported_tier','cache_write_unpriced')),
  pricing_version text check (pricing_version = 'openai-standard-2026-11-13'),
  error_type text check (error_type in ('timeout','rate_limit','authentication','permission','provider_unavailable','invalid_request','network','invalid_response','incomplete_response','provider_error','validation','mail_transport','unexpected')),
  http_status integer check (http_status between 100 and 599),
  retry_count integer not null default 0 check (retry_count between 0 and 100),
  recorded_at timestamptz not null default now(),
  expires_at timestamptz not null default (now()+interval '30 days'),
  unique (span_id,event_type),
  check ((event_type='start' and status='running' and ended_at is null and duration_ms is null)
      or (event_type='finish' and status in ('success','failure') and ended_at >= started_at and duration_ms is not null))
);
create index kekorea_telemetry_started_idx on public.kekorea_telemetry_events(started_at desc);
create index kekorea_telemetry_expiry_idx on public.kekorea_telemetry_events(expires_at);
create index kekorea_telemetry_ai_idx on public.kekorea_telemetry_events(model,started_at desc)
  where task='ai.request' and event_type='finish';
alter table public.kekorea_telemetry_events enable row level security;
revoke all on public.kekorea_telemetry_events from public,anon,authenticated,service_role;
grant select,insert on public.kekorea_telemetry_events to service_role;
comment on table public.kekorea_telemetry_events is 'Private JSON execution metadata only; no identities, prompts, mail, contract contents, credentials or exception messages. 30-day TTL.';

-- The client cannot extend retention by supplying its own expiry.
create function public.kekorea_telemetry_expiry() returns trigger
language plpgsql security invoker set search_path='' as $$
begin
  new.recorded_at := now();
  new.expires_at := least(now(),coalesce(new.ended_at,new.started_at)) + interval '30 days';
  return new;
end;
$$;
revoke all on function public.kekorea_telemetry_expiry() from public,anon,authenticated;
create trigger kekorea_telemetry_set_expiry before insert on public.kekorea_telemetry_events
  for each row execute function public.kekorea_telemetry_expiry();

create function public.kekorea_telemetry_summary(p_days integer default 7) returns jsonb
language sql stable security invoker set search_path='' as $$
with completed as (
  select * from public.kekorea_telemetry_events
  where event_type='finish' and expires_at > now()
    and started_at >= now() - (greatest(1,least(coalesce(p_days,7),30)) * interval '1 day')
), ai as (
  select * from completed where task='ai.request'
), models as (
  select model, count(*) calls,
    count(*) filter (where status='success') successes,
    count(*) filter (where status='failure') failures,
    round(100.0 * count(*) filter (where status='success')/nullif(count(*),0),2) success_rate,
    round(100.0 * count(*) filter (where status='failure')/nullif(count(*),0),2) failure_rate,
    avg(duration_ms) avg_duration_ms,
    percentile_cont(0.95) within group (order by duration_ms) p95_duration_ms,
    sum(input_tokens) input_tokens, sum(output_tokens) output_tokens,
    sum(cached_input_tokens) cached_input_tokens,
    count(*) filter (where input_tokens is null or output_tokens is null) missing_usage_calls,
    sum(estimated_cost_usd) estimated_cost_usd,
    count(*) filter (where estimated_cost_usd is null) unpriced_calls,
    count(*) filter (where retry_count>0) retry_calls
  from ai group by model
), tasks as (
  select task,document_kind,count(*) runs,count(*) filter (where status='failure') failures,
    avg(duration_ms) avg_duration_ms from completed group by task,document_kind
), errors as (
  select task,model,error_type,http_status,count(*) failures
  from completed where status='failure' group by task,model,error_type,http_status
), daily as (
  select (started_at at time zone 'Asia/Seoul')::date as day,model,count(*) calls,
    count(*) filter (where status='failure') failures, sum(estimated_cost_usd) estimated_cost_usd
  from ai group by 1,2
)
select jsonb_build_object(
  'retention_days',30,'generated_at',now(),
  'totals',(select jsonb_build_object('calls',count(*),'failures',count(*) filter (where status='failure'),
    'successes',count(*) filter (where status='success'),
    'avg_duration_ms',avg(duration_ms),'input_tokens',sum(input_tokens),'output_tokens',sum(output_tokens),
    'estimated_cost_usd',sum(estimated_cost_usd),'unpriced_calls',count(*) filter (where estimated_cost_usd is null),
    'missing_usage_calls',count(*) filter (where input_tokens is null or output_tokens is null),
    'retry_calls',count(*) filter (where retry_count>0)) from ai),
  'models',coalesce((select jsonb_agg(to_jsonb(m) order by m.calls desc,m.model) from models m),'[]'::jsonb),
  'tasks',coalesce((select jsonb_agg(to_jsonb(t) order by t.task,t.document_kind) from tasks t),'[]'::jsonb),
  'errors',coalesce((select jsonb_agg(to_jsonb(e) order by e.failures desc) from errors e),'[]'::jsonb),
  'daily',coalesce((select jsonb_agg(to_jsonb(d) order by d.day,d.model) from daily d),'[]'::jsonb)
);
$$;
revoke all on function public.kekorea_telemetry_summary(integer) from public,anon,authenticated;
grant execute on function public.kekorea_telemetry_summary(integer) to service_role;

-- Continues while Streamlit is asleep. Each job is confined to telemetry rows.
create extension if not exists pg_cron with schema pg_catalog;
select cron.schedule('kekorea-telemetry-retention','15 * * * *',
  $job$delete from public.kekorea_telemetry_events where expires_at <= now();$job$);
