"""MASTER GRAPH must reuse the existing KE KOREA Streamlit design tokens.

Regression guard: design-only changes must preserve auth, controls and workflows.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "app.py"
PAGE = ROOT / "orchestration" / "ui" / "streamlit_page.py"


class ThemeParityTests(unittest.TestCase):
    def test_exact_primary_brand_colors_match_existing_app(self):
        from Quotation_KEKOREA.orchestration.ui.ke_theme import STYLE
        reference = SOURCE.read_text(encoding="utf-8")
        for token in ("#092b4c", "#0877c9", "#f5f8fb", "#eaf5fc",
                      "#dbe8f2", "#172b3d", "#16466f", "#065f9f"):
            with self.subTest(token=token):
                self.assertIn(token, reference)
                self.assertIn(token, STYLE)
        self.assertIn(".ke-header", STYLE)
        self.assertIn(".ke-eyebrow", STYLE)
        self.assertIn("[data-testid=\"stSidebar\"]", STYLE)

    def test_theme_asset_points_to_existing_logo_no_duplicate(self):
        from Quotation_KEKOREA.orchestration.ui.ke_theme import logo_path
        self.assertEqual(logo_path().resolve(), (ROOT / "assets" / "company_logo.png").resolve())
        self.assertTrue(logo_path().exists())


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest unavailable")
class ThemeUiTests(unittest.TestCase):
    def test_authenticated_layout_keeps_navigation_and_renders_matching_header(self):
        with patch(
            "Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
            return_value="owner@example.com",
        ):
            app = AppTest.from_file(str(PAGE), default_timeout=25).run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        self.assertTrue(any("KE KOREA" in str(x.value) for x in app.markdown))
        self.assertIn("AI 업무 요청", app.radio[0].options)
        self.assertIn("저장된 계약서", app.radio[0].options)
        self.assertTrue(app.button(key="master_logout"))
        self.assertFalse(any("AI 거래조건 추출" == x for x in app.radio[0].options))


if __name__ == "__main__":
    unittest.main()
