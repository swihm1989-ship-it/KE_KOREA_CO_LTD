"""Regression: one shared fact editor, not multiple independent recovery forms."""
import ast
from pathlib import Path
import unittest


class RecoveryFormSourceTests(unittest.TestCase):
    def test_all_fact_edits_use_one_editor_before_pdf_preview(self):
        source = Path(__file__).resolve().parents[1] / "ui" / "ai_intake_page.py"
        text = source.read_text(encoding="utf-8")
        tree = ast.parse(text)
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertIn("_render_single_editor", functions)
        self.assertIn("_apply_shared_input", functions)
        self.assertIn("render_ai_intake", functions)
        main = ast.get_source_segment(text, functions["render_ai_intake"])
        self.assertEqual(main.count("_render_single_editor(digest, candidates[1])"), 1)
        self.assertLess(main.index("_render_single_editor(digest, candidates[1])"),
                        main.index("st.markdown(\"#### 실시간 반영 결과\")"))
        for name in ("_render_recovery_inputs(", "_render_missing_inputs(",
                     "_render_quick_corrections(", 'with st.form("master_pdf_required_fields")'):
            self.assertNotIn(name, main)
        editor = ast.get_source_segment(text, functions["_render_single_editor"])
        self.assertIn("ai_intake_shared_", editor)
        self.assertIn("_apply_shared_input", editor)
        self.assertIn("on_change=_apply_extra_item", editor)


if __name__ == "__main__":
    unittest.main()
