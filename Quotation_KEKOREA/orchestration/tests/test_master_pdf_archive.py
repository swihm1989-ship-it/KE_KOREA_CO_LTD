"""Regression tests for the authenticated MASTER PDF archive (no network access)."""
from __future__ import annotations

from hashlib import sha256

from streamlit.errors import StreamlitAPIException
from unittest import TestCase
from unittest.mock import Mock, patch

from Quotation_KEKOREA.orchestration.workflows import pdf_archive as archive
from Quotation_KEKOREA.orchestration.ui import pdf_archive_page

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

    def test_delete_owned_final_pdf_metadata_and_private_object(self):
        ident = "18d53c20-c2bc-493d-b992-6a1611f99857"
        path = archive.owner_key("owner@example.test") + "/2026/11/" + ident + ".pdf"
        row = {"id": ident, "kind": "CONTRACT", "status": "final",
               "filename": "Supply-contract.pdf", "storage_path": path}
        self.repo.request.side_effect = [
            [row], None, None, [row],
        ]
        archive.delete_document(self.env, "owner@example.test", ident)
        self.assertEqual(self.repo.request.call_count, 4)
        get_call, parent_patch, child_patch, deleted = self.repo.request.call_args_list
        self.assertEqual(get_call.args[:2], ("GET", archive.TABLE))
        self.assertEqual(deleted.args[:2], ("DELETE", archive.TABLE))
        self.assertEqual(dict(deleted.kwargs["query"])["owner_email"],
                         "eq.owner@example.test")
        self.assertEqual(dict(deleted.kwargs["query"])["status"], "eq.final")
        self.assertEqual(parent_patch.kwargs["payload"], {"final_document_id": None})
        self.assertEqual(child_patch.kwargs["payload"], {"parent_draft_id": None})
        self.repo.delete_private_file.assert_called_once_with(archive.BUCKET, path)

    def test_pdf_delete_cannot_remove_another_owner_storage_path(self):
        ident = "18d53c20-c2bc-493d-b992-6a1611f99857"
        row = {"id": ident, "status": "draft",
               "storage_path": archive.owner_key("someone@example.test") +
                               "/2026/11/" + ident + ".pdf"}
        self.repo.request.return_value = [row]
        with self.assertRaises(archive.PdfArchiveError):
            archive.delete_document(self.env, "owner@example.test", ident)
        self.repo.delete_private_file.assert_not_called()
        self.assertEqual(self.repo.request.call_count, 1)

    def test_failed_metadata_delete_never_purges_storage(self):
        ident = "18d53c20-c2bc-493d-b992-6a1611f99857"
        row = {"id": ident, "status": "draft", "storage_path":
               archive.owner_key("owner@example.test") + "/2026/11/" + ident + ".pdf"}
        self.repo.request.side_effect = [[row], None, None, []]
        with self.assertRaises(archive.PdfArchiveError):
            archive.delete_document(self.env, "owner@example.test", ident)
        self.repo.delete_private_file.assert_not_called()

    def test_storage_cleanup_failure_is_not_misreported_as_complete(self):
        ident = "18d53c20-c2bc-493d-b992-6a1611f99857"
        row = {"id": ident, "status": "final", "storage_path":
               archive.owner_key("owner@example.test") + "/2026/11/" + ident + ".pdf"}
        self.repo.request.side_effect = [[row], None, None, [row]]
        self.repo.delete_private_file.side_effect = OSError("private storage failure")
        with self.assertRaisesRegex(archive.PdfArchiveError, "파일 정리가 실패"):
            archive.delete_document(self.env, "owner@example.test", ident)

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



class MasterPdfArchivePreviewTests(TestCase):
    def test_native_pdf_viewer_receives_exact_stored_bytes(self):
        with patch.object(pdf_archive_page.st, "pdf", create=True) as native:
            with patch("streamlit.components.v1.html") as fallback:
                pdf_archive_page._preview(PDF)
        native.assert_called_once_with(PDF, height=740)
        fallback.assert_not_called()

    def test_missing_pdf_extra_uses_fallback_instead_of_crashing(self):
        with patch.object(
            pdf_archive_page.st, "pdf", create=True,
            side_effect=StreamlitAPIException("streamlit-pdf extra not installed"),
        ) as native:
            with patch("streamlit.components.v1.html") as fallback:
                pdf_archive_page._preview(PDF)
        native.assert_called_once_with(PDF, height=740)
        fallback.assert_called_once()
        html = fallback.call_args.args[0]
        self.assertIn("data:application/pdf;base64,", html)
        self.assertIn("height=\"730\"", html)
        self.assertEqual(fallback.call_args.kwargs["height"], 755)

    def test_native_import_failure_uses_same_fallback(self):
        with patch.object(
            pdf_archive_page.st, "pdf", create=True,
            side_effect=ModuleNotFoundError("No module named 'streamlit_pdf'"),
        ):
            with patch("streamlit.components.v1.html") as fallback:
                pdf_archive_page._preview(PDF)
        fallback.assert_called_once()

if __name__ == "__main__":
    import unittest
    unittest.main()
