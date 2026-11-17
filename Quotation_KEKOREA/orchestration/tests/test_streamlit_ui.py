"""MASTER sidebar routing and safe sample workflow smoke tests."""
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

UI = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"
MENU = ["시장 뉴스", "메일함", "AI 업무 요청", "통합 업무 흐름",
        "문서 검토", "발송 대기", "저장된 계약서"]
HIDDEN = ["업무 대시보드", "실행 기록", "관리자 모니터링",
          "문서 초안 미리보기", "엔진 사전검증"]


class StreamlitMockUiTests(unittest.TestCase):
    def setUp(self):
        for target, result in (
            ("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
             "test@example.com"),
            ("Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news", ([], None)),
        ):
            patched = patch(target, return_value=result)
            patched.start()
            self.addCleanup(patched.stop)

    def app(self):
        app = AppTest.from_file(str(UI), default_timeout=20).run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        return app

    def test_sidebar_exposes_only_essential_menu(self):
        app = self.app()
        options = app.radio[0].options
        self.assertEqual(list(options), MENU)
        self.assertFalse(any(label in options for label in HIDDEN))
        self.assertTrue(any("MASTER GRAPH" in str(v.value) for v in app.markdown))

    def test_document_review_keeps_mock_safety_behavior(self):
        app = self.app()
        # Earlier sample dashboard has been removed but its read-only
        # mock workflow is retained internally for regression coverage.
        from Quotation_KEKOREA.orchestration.workflows.mock_workflow import (
            SAMPLE_MESSAGES, start_mock_run, approve_mock_document)
        sample = SAMPLE_MESSAGES[0]
        run = start_mock_run(sample)
        app.session_state["mock_runs"] = {sample.id: run}
        app.radio[0].set_value("문서 검토").run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        self.assertTrue(any("초안별 검토" in x.value for x in app.subheader))
        self.assertTrue(any(t.kind for t in run.tasks))

    def test_pending_page_does_not_offer_real_mail_send(self):
        app = self.app()
        with patch("Quotation_KEKOREA.orchestration.workflows.pdf_archive.list_documents",
                   return_value=[]):
            app.radio[0].set_value("발송 대기").run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        self.assertTrue(any("발송 대기" in x.value for x in app.subheader))
        self.assertFalse(any("메일 발송" in b.label for b in app.button))


if __name__ == "__main__":
    unittest.main()
