-- Dedicated private schema: no browser/API roles or public table exposure.
create schema if not exists ke_mail_agent;
revoke all on schema ke_mail_agent from public, anon, authenticated;
grant usage on schema ke_mail_agent to service_role;

create table if not exists ke_mail_agent.inbox (
  id bigint generated always as identity primary key,
  account text not null,
  uidl text not null,
  sender text not null default '',
  subject text not null default '',
  received_at text not null default '',
  body text not null default '',
  attachment_names jsonb not null default '[]'::jsonb,
  first_seen_at timestamptz not null default now(),
  status text not null default 'unreviewed'
    check (status in ('unreviewed','review_needed','draft_ready','approved','archived')),
  unique(account, uidl)
);
create index if not exists ke_mail_inbox_account_seen on ke_mail_agent.inbox(account,first_seen_at desc);
alter table ke_mail_agent.inbox enable row level security;
revoke all on ke_mail_agent.inbox from public, anon, authenticated;
grant select, insert, update on ke_mail_agent.inbox to service_role;
grant usage, select on sequence ke_mail_agent.inbox_id_seq to service_role;

create table if not exists ke_mail_agent.poll_runs (
  id bigint generated always as identity primary key,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  result text not null check (result in ('success','partial','failed')),
  count_seen integer not null default 0,
  count_new integer not null default 0,
  note text not null default ''
);
alter table ke_mail_agent.poll_runs enable row level security;
revoke all on ke_mail_agent.poll_runs from public, anon, authenticated;
grant select, insert, update on ke_mail_agent.poll_runs to service_role;
grant usage, select on sequence ke_mail_agent.poll_runs_id_seq to service_role;
