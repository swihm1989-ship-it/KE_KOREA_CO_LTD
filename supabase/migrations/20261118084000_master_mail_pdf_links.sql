-- One-to-many mapping from a human-reviewed reply DRAFT to saved FINAL PDFs.
-- Existing pdf_archive schema/UI and originals are unchanged.
CREATE TABLE IF NOT EXISTS public.kekorea_master_mail_pdf_links (
  owner_email text NOT NULL,
  outbox_id uuid NOT NULL REFERENCES public.kekorea_master_mail_outbox(id) ON DELETE CASCADE,
  pdf_id uuid NOT NULL REFERENCES public.kekorea_master_pdf_archive(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (outbox_id, pdf_id)
);
CREATE INDEX IF NOT EXISTS kekorea_master_mail_pdf_links_owner_pdf_idx
  ON public.kekorea_master_mail_pdf_links(owner_email,pdf_id);
ALTER TABLE public.kekorea_master_mail_pdf_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.kekorea_master_mail_pdf_links FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, DELETE ON public.kekorea_master_mail_pdf_links TO service_role;
