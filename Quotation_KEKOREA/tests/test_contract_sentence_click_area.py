"""Contract sentence selection uses a visible, full-area Streamlit button."""
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests


class SentenceClickAreaTests(ThreeBoxUiTests):
    def test_wrapped_sentence_keeps_one_visible_click_button_and_opens_note(self):
        snapshot = self.repo.revisions["sample"][0]["snapshot"]
        sentence = snapshot["clauses"][0]["sentences"][0]
        sentence["text"] = ("Delivery Terms: EXW Hanwha Jincheon Warehouse, "
                            "collection before 31.Dec.2026. " * 5).strip()
        self.run_app()
        button = self.at.button(key="contract_sentence_sample_s1")
        self.assertIn("Delivery Terms", button.label)
        button.click()
        self.run_app()
        self.assertTrue(any(
            a.key == "contract_note_sample_1_s1" for a in self.at.text_area
        ))

    def test_click_area_css_has_no_invisible_absolute_overlay(self):
        ui = (Path(__file__).parents[1] / "contracts" / "ui.py").read_text(encoding="utf-8")
        begin = ui.index("/* Use the visible Streamlit button as the complete click surface.")
        end = ui.index(".contract-full-sentence-hover", begin)
        rules = ui[begin:end]
        self.assertIn("position:static!important", rules)
        self.assertIn("height:auto!important", rules)
        self.assertIn("opacity:1!important", rules)
        self.assertNotIn("opacity:0!important", rules)
        self.assertNotIn("position:absolute!important", rules)


if __name__ == "__main__":
    unittest.main()
