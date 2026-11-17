"""Regression tests for the authenticated MASTER PDF archive (no network access)."""
from __future__ import annotations

from hashlib import sha256
from unittest import TestCase
from unittest.mock import Mock, patch

from Quotation_KEKOREA.orchestration.workflows import pdf_archive as archive

PDF = b"%PDF-1.4\nsynthetic PDF bytes\n%%EOF"
SOURCE = {"document_type": "PI", "document_number": "PI-TEST"}


class MasterPdfArchiveTests(TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.request.return_value = [{
            "id": "18d53c20-c2bc-493d-b992-6a1611f99857",
            "filename": "PI-TEST.pdf", "created_at": "2026-11-17T06:45:00+00:00",
            "status": "draft", "kind": "PI",
        }]
        self.patch_repo = patch.object(archive, "ContractRepository", return_value=self.repo)
        self.patch_repo.start()
        self.addCleanup(self.patch_repo.stop)
        self.env = {"SUPABASE_URL": "https://test.supabase.co",
                    "SUPABASE_SECRET_KEY": "TEST_SERVER_ONLY"}

    def test_only_real_pdf_with_authenticated_owner_can_be_stored(self):
        with self.assertRaises(archive.PdfArchiveError):
            archive.archive_pdf(self.env, "", "PI", "draft",
                                {"filename": "PI.pdf", "content": PDF}, SOURCE)
        with self.assertRaises(archive.PdfArchiveError):
            archive.archive_pdf(self.env, "owner@example.test", "PI", "final",
                                {"filename": "PI.pdf", "content": b"not-a-pdf"}, SOURCE)
        self.repo.upload_private_file.assert_not_called()

    def test_archive_uploads_private_pdf_then_commits_status_and_source(self):
        row = archive.archive_pdf(
            self.env, "OWNER@example.test", "PI", "draft",
            {"filename": "PI-TEST.pdf", "content": PDF}, SOURCE)
        self.assertEqual(row["status"], "draft")
        upload = self.repo.upload_private_file.call_args
        self.assertEqual(upload.args[0], archive.BUCKET)
        self.assertEqual(upload.args[3], "application/pdf")
        self.assertEqual(archive.owner_key("OWNER@example.test"), archive.owner_key("owner@example.test"))
        self.assertNotIn("owner@example.test", upload.args[1])
        commit = self.repo.request.call_args
        self.assertEqual(commit.args[:2], ("POST", archive.TABLE))
        record = commit.kwargs["payload"]
        self.assertEqual(record["status"], "draft")
        self.assertEqual(record["owner_email"], "owner@example.test")
        self.assertEqual(record["source_snapshot"], SOURCE)
        self.assertEqual(record["content_sha256"], sha256(PDF).hexdigest())
        self.assertEqual(record["source_fingerprint"], archive.source_fingerprint(SOURCE))

    def test_db_failure_rolls_back_unreferenced_upload(self):
        self.repo.request.side_effect = RuntimeError("synthetic database failure")
        with self.assertRaises(archive.PdfArchiveError):
            archive.archive_pdf(self.env, "owner@example.test", "PI", "draft",
                                {"filename": "PI.pdf", "content": PDF}, SOURCE)
        self.repo.delete_private_file.assert_called_once()

    def test_listing_filters_owner_and_status(self):
        archive.list_documents(self.env, "Owner@Example.test", "draft")
        query = dict(self.repo.request.call_args.kwargs["query"])
        self.assertEqual(query["owner_email"], "eq.owner@example.test")
        self.assertEqual(query["status"], "eq.draft")
        self.assertNotIn("source_snapshot", query["select"])

    def test_download_verifies_authenticated_row_and_checksum(self):
        ident = "18d53c20-c2bc-493d-b992-6a1611f99857"
        self.repo.request.return_value = [{
            "id": ident, "storage_path": archive.owner_key("owner@example.test") + "/record.pdf",
            "filename": "PI-TEST.pdf", "kind": "PI", "status": "draft",
            "content_sha256": sha256(PDF).hexdigest(), "source_snapshot": SOURCE,
        }]
        self.repo.download_private_file.return_value = PDF
        row, content = archive.load_pdf(self.env, "owner@example.test", ident)
        self.assertEqual(content, PDF)
        self.assertEqual(row["kind"], "PI")
        query = dict(self.repo.request.call_args.kwargs["query"])
        self.assertEqual(query["owner_email"], "eq.owner@example.test")
        self.repo.download_private_file.return_value = b"%PDF-tampered"
        with self.assertRaises(archive.PdfArchiveError):
            archive.load_pdf(self.env, "owner@example.test", ident)

    def test_mark_converted_only_updates_owned_pending_draft(self):
        draft_id = "18d53c20-c2bc-493d-b992-6a1611f99857"
        final_id = "8a7dc566-ed74-4b9b-b2d5-9e7b2aeb53b0"
        archive.mark_draft_converted(self.env, "owner@example.test", draft_id, final_id)
        call = self.repo.request.call_args
        self.assertEqual(call.args[:2], ("PATCH", archive.TABLE))
        self.assertEqual(call.kwargs["payload"]["status"], "converted")
        query = dict(call.kwargs["query"])
        self.assertEqual(query["status"], "eq.draft")
        self.assertEqual(query["owner_email"], "eq.owner@example.test")


if __name__ == "__main__":
    import unittest
    unittest.main()
