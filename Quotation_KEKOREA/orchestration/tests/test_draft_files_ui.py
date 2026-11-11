"""Streamlit smoke test: real draft file bytes in isolated preview UI."""
import unittest
from pathlib import Path
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

UI = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class DraftFileUiTests(unittest.TestCase):
    def test_trade_draft_download_from_existing_preview(self):
        app = AppTest.from_file(str(UI), default_timeout=20).run()
        app.radio[0].set_value("문서 초안 미리보기").run()
        app.button(key="build_readonly_preview").click().run()
        app.button(key="create_review_files").click().run()
        self.assertEqual(len(app.exception), 0, [str(x.message) for x in app.exception])
        self.assertIn("docx", app.session_state["review_file_bundle"])
        self.assertNotIn("pdf", app.session_state["review_file_bundle"])
        self.assertFalse(app.session_state["review_file_bundle"]["docx"]["sendable"])

    def test_no_contract_draft_export_without_authored_clauses(self):
        app = AppTest.from_file(str(UI), default_timeout=20).run()
        app.radio[0].set_value("문서 초안 미리보기").run()
        app.selectbox[0].set_value("CONTRACT").run()
        app.button(key="build_readonly_preview").click().run()
        app.button(key="create_review_files").click().run()
        self.assertEqual(len(app.exception), 0, [str(x.message) for x in app.exception])
        self.assertFalse(app.session_state.get("review_file_bundle"))


if __name__ == "__main__":
    unittest.main()
