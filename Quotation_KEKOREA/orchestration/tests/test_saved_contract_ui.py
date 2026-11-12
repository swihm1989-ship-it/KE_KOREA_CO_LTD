"""Login barrier and private contract list UI tests."""
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

PAGE = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class AuthenticatedLibraryUiTests(unittest.TestCase):
    def setUp(self):
        news = patch("Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
                     return_value=([], None))
        news.start()
        self.addCleanup(news.stop)

    @patch.dict(os.environ, {"ORCHESTRATION_ALLOWED_EMAILS": "owner@example.com"})
    def test_unauthenticated_user_cannot_see_any_workspace_page(self):
        app = AppTest.from_file(str(PAGE), default_timeout=20).run()
        self.assertEqual(len(app.exception), 0, [x.message for x in app.exception])
        self.assertTrue(any("ke-login-hero" in x.value for x in app.markdown))
        self.assertFalse(app.radio)
        self.assertFalse(app.selectbox)

    def test_authorized_reader_lists_and_opens_existing_contract_revision(self):
        repo = Mock()
        repo.list_contracts.return_value = [
            {"id": "existing-1", "title": "Supply Contract", "contract_type": "sale",
             "language": "en", "status": "draft", "current_revision": 2, "updated_at": "2026-11-11"}]
        repo.load_contract.return_value = [{
            "revision": 2, "created_at": "2026-11-11", "change_summary": "Updated",
            "snapshot": {
                "contract_id": "existing-1", "revision": 2, "contract_type": "sale",
                "language": "en", "title": "Supply Contract", "parties": [],
                "terms": [], "clauses": [{
                    "title": "Scope", "order": 1,
                    "sentences": [{"id": "s1", "text": "Stored and approved original clause."}]
                }], "issues": [],
            }
        }]
        with patch.dict(os.environ, {"SUPABASE_URL": "https://demo.supabase.co", "SUPABASE_SECRET_KEY": "fake-test-key"}), patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication", return_value="owner@example.com"), patch(
            "Quotation_KEKOREA.orchestration.ui.saved_contracts.make_reader", return_value=repo
        ):
            app = AppTest.from_file(str(PAGE), default_timeout=25).run()
            app.radio[0].set_value("저장된 계약서").run()
            self.assertEqual(len(app.exception), 0, [x.message for x in app.exception])
            self.assertTrue(any("Supply Contract" in str(v.value) for v in app.markdown))
            self.assertTrue(any("Stored and approved original clause." in str(v.value) for v in app.markdown) or
                            any("Stored and approved original clause." in str(v.value) for v in app.text))
            repo.load_contract.assert_called_with("existing-1")
            repo.commit_revision.assert_not_called()
            repo.delete_private_file.assert_not_called()
            repo.save_export.assert_not_called()


if __name__ == "__main__":
    unittest.main()
