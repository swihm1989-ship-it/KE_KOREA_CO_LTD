"""New structured preview UI must render a guarded trade draft."""
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

UI = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class PreviewUITest(unittest.TestCase):
    def test_trade_demo_preview_never_marks_final_or_sends(self):
        app = AppTest.from_file(str(UI), default_timeout=20).run()
        app.radio[0].set_value("문서 초안 미리보기").run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        app.button(key="build_readonly_preview").click().run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(app.session_state["preview_current"].watermark, "DRAFT - NOT FOR ISSUE")
        self.assertTrue(any("발송 권한 없음" in x.value for x in app.caption))
        self.assertTrue(any("20.00" in str(x.value) for x in app.metric))

    def test_empty_contract_does_not_invent_language(self):
        app = AppTest.from_file(str(UI), default_timeout=20).run()
        app.radio[0].set_value("문서 초안 미리보기").run()
        app.selectbox[0].set_value("CONTRACT").run()
        app.button(key="build_readonly_preview").click().run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertTrue(any("미확정 항목" in x.label for x in app.expander))


if __name__ == "__main__":
    unittest.main()
