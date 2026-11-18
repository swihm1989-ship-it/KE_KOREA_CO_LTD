"""Verify production sidebar excludes only the legacy demonstration screens."""
from pathlib import Path
import ast
import unittest


PAGE = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"
EXPECTED = ["시장 뉴스", "메일함", "AI 업무 요청", "발송 대기", "저장된 계약서"]


class MasterSidebarMenuTest(unittest.TestCase):
    def test_production_menu_has_exactly_five_real_workflow_items(self):
        tree = ast.parse(PAGE.read_text(encoding="utf-8"))
        menus = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_master_menu"
                    for t in node.targets)
        ]
        self.assertEqual(len(menus), 1)
        self.assertEqual(ast.literal_eval(menus[0]), EXPECTED)

    def test_legacy_handlers_retained_but_not_exposed_in_sidebar(self):
        text = PAGE.read_text(encoding="utf-8")
        self.assertIn('elif page == "통합 업무 흐름":', text)
        self.assertIn('elif page in ("문서 검토", "발송 대기", "실행 기록"):', text)
        self.assertIn('st.sidebar.radio("업무 메뉴", _master_menu', text)

    def test_navigation_to_removed_selection_falls_back_to_ai_intake(self):
        text = PAGE.read_text(encoding="utf-8")
        self.assertIn('if st.session_state.get("master_page") not in (None, *_master_menu):', text)
        self.assertIn('st.session_state["master_page"] = "AI 업무 요청"', text)


if __name__ == "__main__":
    unittest.main()
