begin;

create table if not exists public.kekorea_contracts (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    contract_type text not null check (contract_type in ('sale', 'trade_commission', 'investment_commission')),
    language text not null check (language in ('ko', 'en')),
    status text not null default 'draft',
    current_revision integer not null default 1 check (current_revision > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.kekorea_contract_revisions (
    contract_id uuid not null references public.kekorea_contracts(id) on delete cascade,
    revision integer not null check (revision > 0),
    snapshot jsonb not null,
    change_summary text not null default '',
    created_at timestamptz not null default now(),
    primary key (contract_id, revision)
);

create table if not exists public.kekorea_contract_messages (
    id uuid primary key default gen_random_uuid(),
    contract_id uuid not null references public.kekorea_contracts(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system')),
    content text not null,
    created_at timestamptz not null default now()
);

create table if not exists public.kekorea_contract_annotations (
    id uuid primary key,
    contract_id uuid not null references public.kekorea_contracts(id) on delete cascade,
    sentence_id text not null,
    base_revision integer not null,
    instruction text not null,
    proposal jsonb,
    status text not null check (status in ('note', 'proposed', 'applied', 'dismissed', 'stale')),
    created_at timestamptz not null default now()
);

create table if not exists public.kekorea_contract_references (
    id uuid primary key default gen_random_uuid(),
    contract_id uuid references public.kekorea_contracts(id) on delete cascade,
    filename text not null,
    content_hash text not null,
    storage_path text,
    extraction_status text not null,
    extracted_text text not null default '',
    source_locations jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    unique (contract_id, content_hash)
);

create table if not exists public.kekorea_preferred_clauses (
    id uuid primary key default gen_random_uuid(),
    text text not null,
    language text not null check (language in ('ko', 'en')),
    contract_types text[] not null default '{}',
    roles text[] not null default '{}',
    category text not null,
    source_refs jsonb not null default '[]'::jsonb,
    approved_at timestamptz not null default now(),
    active boolean not null default true
);

create table if not exists public.kekorea_contract_exports (
    id uuid primary key default gen_random_uuid(),
    contract_id uuid not null references public.kekorea_contracts(id) on delete cascade,
    revision integer not null,
    language text not null check (language in ('ko', 'en')),
    format text not null check (format in ('docx', 'pdf')),
    storage_path text not null,
    content_hash text not null,
    created_at timestamptz not null default now()
);

create index if not exists kekorea_contracts_updated_at_idx
    on public.kekorea_contracts(updated_at desc);
create index if not exists kekorea_contract_messages_contract_idx
    on public.kekorea_contract_messages(contract_id, created_at);
create index if not exists kekorea_contract_references_hash_idx
    on public.kekorea_contract_references(content_hash);

alter table public.kekorea_contracts enable row level security;
alter table public.kekorea_contract_revisions enable row level security;
alter table public.kekorea_contract_messages enable row level security;
alter table public.kekorea_contract_annotations enable row level security;
alter table public.kekorea_contract_references enable row level security;
alter table public.kekorea_preferred_clauses enable row level security;
alter table public.kekorea_contract_exports enable row level security;

revoke all on public.kekorea_contracts, public.kekorea_contract_revisions,
    public.kekorea_contract_messages, public.kekorea_contract_annotations,
    public.kekorea_contract_references, public.kekorea_preferred_clauses,
    public.kekorea_contract_exports from anon, authenticated;
grant select, insert, update, delete on public.kekorea_contracts,
    public.kekorea_contract_revisions, public.kekorea_contract_messages,
    public.kekorea_contract_annotations, public.kekorea_contract_references,
    public.kekorea_preferred_clauses, public.kekorea_contract_exports to service_role;

insert into storage.buckets (id, name, public, file_size_limit)
values ('kekorea-contracts', 'kekorea-contracts', false, 20971520)
on conflict (id) do update set public = false, file_size_limit = 20971520;

create or replace function public.kekorea_contract_create(p_contract jsonb, p_snapshot jsonb)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
    new_id uuid;
begin
    if current_setting('request.jwt.claim.role', true) <> 'service_role' then
        raise insufficient_privilege using message = 'service_role_required';
    end if;
    insert into public.kekorea_contracts (title, contract_type, language, status)
    values (coalesce(nullif(p_contract->>'title', ''), 'Untitled contract'),
            p_contract->>'contract_type', p_contract->>'language',
            coalesce(p_contract->>'status', 'draft'))
    returning id into new_id;
    p_snapshot := jsonb_set(p_snapshot, '{contract_id}', to_jsonb(new_id::text), true);
    p_snapshot := jsonb_set(p_snapshot, '{revision}', '1'::jsonb, true);
    insert into public.kekorea_contract_revisions (contract_id, revision, snapshot, change_summary)
    values (new_id, 1, p_snapshot, 'Contract created');
    return jsonb_build_object('id', new_id, 'current_revision', 1);
end;
$$;

create or replace function public.kekorea_contract_commit_revision(
    p_contract_id uuid, p_expected_revision integer, p_snapshot jsonb, p_change_summary text
) returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
    current_rev integer;
    next_rev integer;
begin
    if current_setting('request.jwt.claim.role', true) <> 'service_role' then
        raise insufficient_privilege using message = 'service_role_required';
    end if;
    select current_revision into current_rev from public.kekorea_contracts
      where id = p_contract_id for update;
    if current_rev is null or current_rev <> p_expected_revision then
        return jsonb_build_object('error', 'revision_conflict');
    end if;
    next_rev := current_rev + 1;
    p_snapshot := jsonb_set(p_snapshot, '{contract_id}', to_jsonb(p_contract_id::text), true);
    p_snapshot := jsonb_set(p_snapshot, '{revision}', to_jsonb(next_rev), true);
    insert into public.kekorea_contract_revisions (contract_id, revision, snapshot, change_summary)
    values (p_contract_id, next_rev, p_snapshot, left(coalesce(p_change_summary, ''), 500));
    update public.kekorea_contracts
       set title = coalesce(nullif(p_snapshot->>'title', ''), title),
           contract_type = p_snapshot->>'contract_type',
           language = p_snapshot->>'language',
           current_revision = next_rev,
           updated_at = now()
     where id = p_contract_id;
    return jsonb_build_object('revision', next_rev);
end;
$$;

create or replace function public.kekorea_contract_delete(p_contract_id uuid)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
begin
    if current_setting('request.jwt.claim.role', true) <> 'service_role' then
        raise insufficient_privilege using message = 'service_role_required';
    end if;
    delete from public.kekorea_contracts where id = p_contract_id;
    return jsonb_build_object('deleted', found);
end;
$$;

revoke all on function public.kekorea_contract_create(jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.kekorea_contract_commit_revision(uuid, integer, jsonb, text) from public, anon, authenticated;
revoke all on function public.kekorea_contract_delete(uuid) from public, anon, authenticated;
grant execute on function public.kekorea_contract_create(jsonb, jsonb) to service_role;
grant execute on function public.kekorea_contract_commit_revision(uuid, integer, jsonb, text) to service_role;
grant execute on function public.kekorea_contract_delete(uuid) to service_role;

commit;
