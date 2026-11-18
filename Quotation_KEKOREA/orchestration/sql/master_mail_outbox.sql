-- KE KOREA MASTER email reply outbox (human-approved sending ONLY).
-- Supabase server-only Data API. No cron, triggers, mail jobs or auto-send.
create table if not exists public.kekorea_master_mail_outbox (
  id uuid primary key default gen_random_uuid(),
  owner_email text not null,
  mailbox_hash text not null,
  mail_uid text not null,
  sender_header text not null,
  recipient_email text not null,
  source_subject text not null,
  source_body text not null,
  source_hash text not null,
  message_id text not null default '',
  candidate_bodies jsonb not null default '[]'::jsonb,
  language text not null default 'en' check (language in ('ko','en')),
  status text not null default 'draft'
    check (status in ('draft','sending','sent','send_unknown')),
  approved_subject text,
  approved_body text,
  approved_sha256 text,
  send_started_at timestamptz,
  sent_at timestamptz,
  created_at timestamptz not null default now(),
  unique (owner_email, mailbox_hash, mail_uid)
);
create index if not exists kekorea_master_mail_outbox_owner_created
  on public.kekorea_master_mail_outbox(owner_email,created_at desc);
alter table public.kekorea_master_mail_outbox enable row level security;
revoke all on table public.kekorea_master_mail_outbox from public, anon, authenticated;
grant select, insert, update, delete on table public.kekorea_master_mail_outbox to service_role;
-- Server only: no public/anon/authenticated RLS allow policy. No SECURITY DEFINER.
