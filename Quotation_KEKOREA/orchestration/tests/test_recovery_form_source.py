"""Regression tests for the unconditional AI intake recovery form."""
import ast
from pathlib import Path
import unittest


class RecoveryFormSourceTests(unittest.TestCase):
    def test_form_is_independent_of_candidate_map(self):
        source = Path(__file__).resolve().parents[1] / "ui" / "ai_intake_page.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertIn("_render_recovery_inputs", functions)
        self.assertIn("render_ai_intake", functions)
        main = ast.get_source_segment(source.read_text(encoding="utf-8"), functions["render_ai_intake"])
        self.assertLess(main.index("_render_recovery_inputs(digest, analysis, requested)"),
                        main.index("current = st.session_state.get(\"ai_intake_candidates\")"))
        recovery = ast.get_source_segment(source.read_text(encoding="utf-8"), functions["_render_recovery_inputs"])
        for label in ("Buyer · 구매자 법인명", "Seller · 판매자 법인명", "통화 · USD 등"):
            self.assertIn(label, recovery)


if __name__ == "__main__":
    unittest.main()
