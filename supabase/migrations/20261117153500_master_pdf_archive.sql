-- Dedicated private PDF output archive; existing contract tables remain unchanged.
CREATE TABLE IF NOT EXISTS public.kekorea_master_pdf_archive (
  id uuid primary key default gen_random_uuid(),
  owner_email text not null check (length(trim(owner_email)) > 3),
  kind text not null check (kind in ('PI','PO','CI','PL','CONTRACT')),
  status text not null check (status in ('draft','final','converted')),
  filename text not null check (length(trim(filename)) > 0),
  storage_path text not null unique,
  content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
  source_fingerprint text not null check (source_fingerprint ~ '^[0-9a-f]{64}$'),
  source_snapshot jsonb not null default '{}'::jsonb,
  parent_draft_id uuid unique references public.kekorea_master_pdf_archive(id),
  final_document_id uuid references public.kekorea_master_pdf_archive(id),
  created_at timestamptz not null default now(),
  converted_at timestamptz,
  check (jsonb_typeof(source_snapshot) = 'object')
);
CREATE INDEX IF NOT EXISTS kekorea_master_pdf_owner_status_time
  ON public.kekorea_master_pdf_archive (owner_email, status, created_at DESC);
ALTER TABLE public.kekorea_master_pdf_archive ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.kekorea_master_pdf_archive FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.kekorea_master_pdf_archive TO service_role;
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('kekorea-master-pdfs', 'kekorea-master-pdfs', false, 20971520,
        ARRAY['application/pdf']::text[])
ON CONFLICT (id) DO NOTHING;
