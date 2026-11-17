"""Public KE KOREA PI: 49 valid numeric quantities must not mean 49 manual unit edits.

Synthetic Lenovo-like computer orders only; no real customer data or API calls.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.agent.document_engine import _synchronize_extracted_quantities
from Quotation_KEKOREA.agent.review_fields import (
    apply_common_quantity_unit, missing_review_fields,
)
from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
from Quotation_KEKOREA.tests.test_review_fields import complete_draft
from Quotation_KEKOREA.tests.auth_test_helpers import isolated_authenticated_ui_tests


def laptop_order():
    doc = complete_draft()
    doc.update(document_type="PI", product_family="other", currency="USD")
    doc["seller"].update(legal_name="KE KOREA CO. LTD", address="Seoul, South Korea")
    doc["buyer"].update(legal_name="SYNTHETIC PARTS PTE LTD", address="Singapore")
    doc["items"] = [
        {"product_name": f"Synthetic Laptop Model {i:02d}",
         "quantity": str(90 + i), "paid_quantity": str(90 + i),
         "shipped_quantity": str(90 + i), "free_quantity": "0",
         "unit": None, "unit_price": "2600", "price_basis": "USD",
         "discount_percent": "0", "source": f"Model {i:02d} Qty {90+i} USD 2600"}
        for i in range(1, 50)
    ]
    return doc


class PublicQuantityUnitRepairTests(unittest.TestCase):
    def test_49_numeric_quantities_without_units_are_distinct_from_missing_quantities(self):
        doc = laptop_order()
        fields = missing_review_fields(doc)
        self.assertEqual(len(fields), 49)
        self.assertTrue(all(f.path[-1] == "unit" for f in fields))
        self.assertEqual([i["paid_quantity"] for i in doc["items"][:2]], ["91", "92"])
        self.assertEqual(doc["items"][0]["unit_price"], "2600")

    def test_bulk_fill_repairs_only_missing_units_without_touching_amounts_or_explicit_units(self):
        doc = laptop_order()
        doc["items"][7]["unit"] = "KG"
        source = deepcopy(doc)
        changed = apply_common_quantity_unit(doc, "PCS")
        self.assertEqual(len(changed), 48)
        self.assertNotIn(7, changed)
        self.assertEqual(doc["items"][7]["unit"], "KG")
        self.assertEqual(doc["items"][0]["unit"], "PCS")
        for before, after in zip(source["items"], doc["items"]):
            for key in ("quantity", "paid_quantity", "shipped_quantity", "free_quantity",
                        "unit_price", "discount_percent", "price_basis", "product_name"):
                self.assertEqual(after[key], before[key], (key, before, after))
        self.assertEqual(missing_review_fields(doc), [])
        self.assertTrue(validate_and_calculate(doc)["ready_for_issue"])

    def test_bulk_fill_rejects_unknown_units_and_does_not_mutate_inputs(self):
        doc = laptop_order()
        source = deepcopy(doc)
        with self.assertRaises(ValueError):
            apply_common_quantity_unit(doc, "UNVERIFIED_OR_INVALID")
        self.assertEqual(doc, source)

    def test_explicit_per_piece_basis_recovers_only_countable_other_items(self):
        doc = laptop_order()
        doc["items"][0]["price_basis"] = "USD/PC"
        doc["items"][1]["price_basis"] = "per piece"
        doc["items"][2]["price_basis"] = "USD/KG"
        doc["items"][3]["unit"] = "SET"
        doc["items"][3]["price_basis"] = "PCS"
        _synchronize_extracted_quantities(doc)
        self.assertEqual(doc["items"][0]["unit"], "PCS")
        self.assertEqual(doc["items"][1]["unit"], "PCS")
        self.assertIsNone(doc["items"][2]["unit"])
        self.assertEqual(doc["items"][3]["unit"], "SET")
        self.assertIsNone(doc["items"][4]["unit"])

    def test_no_watt_or_mass_unit_inferred_from_price_basis_without_quantity_unit(self):
        doc = laptop_order()
        doc["product_family"] = "solar_cell"
        doc["items"][0]["price_basis"] = "USD/PC"
        _synchronize_extracted_quantities(doc)
        self.assertIsNone(doc["items"][0]["unit"])


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "Streamlit not installed")
@isolated_authenticated_ui_tests
class PublicQuantityUnitUiTests(unittest.TestCase):
    def test_49_row_pi_has_one_bulk_unit_action_and_after_confirmation_pdf_enabled(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        doc = laptop_order()
        env = {"OPENAI_API_KEY": "TEST", **{f"KEKOREA_USD_{name}": "TEST"
               for name in ("BENEFICIARY", "BANK_NAME", "BRANCH", "SWIFT",
                            "ACCOUNT_NUMBER", "BANK_ADDRESS")}}
        with (patch("Quotation_KEKOREA.agent.extractor.load_env", return_value=env),
              patch("Quotation_KEKOREA.agent.pricing.load_local_seed", return_value={"products": []}),
              patch("Quotation_KEKOREA.agent.branding.resolve_company_seal",
                    return_value=(app_path, b"TEST-SEAL", None))):
            at = AppTest.from_file(str(app_path), default_timeout=35)
            at.session_state["selected_document_page"] = "PI 만들기"
            at.session_state["trade_draft"] = doc
            at.session_state["trade_draft_page"] = "PI 만들기"
            at.run()
            self.assertFalse(at.exception, [x.message for x in at.exception])
            self.assertTrue(any("49" in warning.value and "수량 단위" in warning.value
                                for warning in at.warning))
            self.assertFalse(any("Item 49: quantity unit" in warning.value
                                 for warning in at.warning))
            self.assertTrue(next(button for button in at.button
                                 if button.key == "bulk_unit_apply_PI 만들기"))
            self.assertTrue(next(button for button in at.button
                                 if button.label == "Create PDF").disabled)
            at.button(key="bulk_unit_apply_PI 만들기").click().run()
            self.assertFalse(at.exception, [x.message for x in at.exception])
            effective = json.loads(at.session_state["rendered_json"])["document"]
            self.assertEqual(len(effective["items"]), 49)
            self.assertTrue(all(row["unit"] == "PCS" for row in effective["items"]))
            self.assertEqual(effective["items"][0]["paid_quantity"], "91")
            self.assertEqual(effective["items"][0]["final_unit_price"], "2600")
            self.assertEqual(effective["items"][0]["discount_percent"], "0")
            self.assertFalse(next(button for button in at.button
                                  if button.label == "Create PDF").disabled)
            self.assertEqual(at.session_state.get("rendered_paths"), {})


if __name__ == "__main__":
    unittest.main()
