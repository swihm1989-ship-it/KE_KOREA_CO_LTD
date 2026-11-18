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


-- AUTO-ACK IS OFF BY DEFAULT. Apply before enabling the separate cron worker.
-- Do not expose any of these rows to the Data API or app browser roles.
alter table ke_mail_agent.inbox add column if not exists message_id text not null default '';
alter table ke_mail_agent.inbox add column if not exists reply_to text not null default '';
alter table ke_mail_agent.inbox add column if not exists auto_submitted text not null default '';
alter table ke_mail_agent.inbox add column if not exists list_id text not null default '';
alter table ke_mail_agent.inbox add column if not exists precedence text not null default '';

create table if not exists ke_mail_agent.auto_reply_intents (
  id bigint generated always as identity primary key,
  account text not null,
  uidl text not null,
  recipient text not null,
  subject text not null,
  body text not null,
  in_reply_to text not null,
  status text not null default 'pending'
    check (status in ('pending','claimed','sent','send_unknown')),
  created_at timestamptz not null default now(),
  claimed_at timestamptz,
  finished_at timestamptz,
  unique(account,uidl),
  foreign key(account,uidl) references ke_mail_agent.inbox(account,uidl)
);
create index if not exists ke_mail_auto_ack_account_recent
  on ke_mail_agent.auto_reply_intents(account,created_at desc);
alter table ke_mail_agent.auto_reply_intents enable row level security;
revoke all on ke_mail_agent.auto_reply_intents from public, anon, authenticated;
grant select, insert, update on ke_mail_agent.auto_reply_intents to service_role;
grant usage, select on sequence ke_mail_agent.auto_reply_intents_id_seq to service_role;
