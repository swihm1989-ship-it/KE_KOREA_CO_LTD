"""User-fillable missing trade/contract facts; never auto-approve AI-extracted facts."""
import copy
import unittest

from Quotation_KEKOREA.orchestration.workflows.intake_followups import (
    missing_fields, apply_answer, format_field_label,
)


def candidates():
    return {
        "PI": {
            "document_type": "PI", "product_family": "solar_cell", "document_number": "DRAFT",
            "currency": "USD", "seller": {"legal_name": "", "address": ""},
            "buyer": {"legal_name": "", "address": ""},
            "incoterms": "EXW Jincheon", "payment_terms": "10% deposit; 90% balance",
            "items": [{"product_name": "M10 PERC", "quantity": "1000000", "unit": "PCS",
                       "unit_price": "0.225", "price_basis": "PCS", "price_source": ""}],
        },
        "CONTRACT": {
            "contract_id": "orchestration-test", "contract_type": "sale", "revision": 1,
            "language": "en", "parties": [], "terms": [
                {"key": "products", "value": "M10 PERC", "status": "suggested", "source_refs": []}
            ],
            "clauses": [], "issues": [], "reference_ids": [], "omissions": {},
        },
    }


class FollowupTests(unittest.TestCase):
    def test_find_missing_buyer_and_seller_and_price_source(self):
        keys = [x.key for x in missing_fields(candidates())]
        self.assertIn("buyer.legal_name", keys)
        self.assertIn("seller.legal_name", keys)
        self.assertIn("buyer.address", keys)
        self.assertIn("seller.address", keys)
        self.assertIn("item.price_source", keys)
        self.assertNotIn("item.quantity", keys)

    def test_answer_buyer_updates_pi_and_contract_without_mutating_input(self):
        original = candidates()
        before = copy.deepcopy(original)
        changed = apply_answer(original, "buyer.legal_name", "TENGYAO TECHNOLOGY CO. LTD")
        self.assertEqual(original, before)
        self.assertEqual(changed["PI"]["buyer"]["legal_name"], "TENGYAO TECHNOLOGY CO. LTD")
        buyer = next(x for x in changed["CONTRACT"]["parties"] if "buyer" in x["roles"])
        self.assertEqual(buyer["legal_name"], "TENGYAO TECHNOLOGY CO. LTD")
        self.assertEqual(buyer["status"], "suggested")
        self.assertEqual(buyer["source_refs"], [])
        self.assertNotIn("buyer.legal_name", [x.key for x in missing_fields(changed)])

    def test_seller_country_only_affects_contract_and_does_not_guess(self):
        changed = apply_answer(candidates(), "seller.country", "Korea")
        seller = next(x for x in changed["CONTRACT"]["parties"] if "seller" in x["roles"])
        self.assertEqual(seller["country"], "Korea")
        self.assertEqual(seller["status"], "suggested")

    def test_answer_required_trade_price_source(self):
        changed = apply_answer(candidates(), "item.price_source", "Buyer written email dated 2026-11-11")
        self.assertEqual(changed["PI"]["items"][0]["price_source"], "Buyer written email dated 2026-11-11")
        self.assertNotIn("item.price_source", [x.key for x in missing_fields(changed)])

    def test_blank_answer_rejected_and_unknown_key_rejected(self):
        for key, val in (("buyer.legal_name", " "), ("buyer.anything", "Buyer"), ("item.quantity", "abc")):
            with self.assertRaises(ValueError):
                apply_answer(candidates(), key, val)

    def test_answer_price_and_terms_updates_both_candidates_but_is_not_confirmed(self):
        changed = apply_answer(candidates(), "item.product_name", "Hanwha M10 PERC 23.2%+")
        self.assertEqual(changed["PI"]["items"][0]["product_name"], "Hanwha M10 PERC 23.2%+")
        terms = [t for t in changed["CONTRACT"]["terms"] if t["key"] == "products"]
        self.assertEqual(terms[0]["value"], "Hanwha M10 PERC 23.2%+")
        self.assertEqual(terms[0]["status"], "suggested")

    def test_new_material_answer_clears_generated_contract_clauses(self):
        original = candidates()
        original["CONTRACT"]["clauses"] = [{"title": "Price", "sentences": [{"text": "Outdated 0.225 price"}]}]
        updated = apply_answer(original, "buyer.address", "Unit 7, Wuxi, China")
        self.assertEqual(updated["CONTRACT"]["clauses"], [])

    def test_missing_fields_excludes_irrelevant_ci_pl_requirements(self):
        self.assertFalse(any(field.key == "shipment_reference" for field in missing_fields(candidates())))
        self.assertIn("item.price_source", [x.key for x in missing_fields(candidates())])
        self.assertTrue(format_field_label("buyer.legal_name"))


if __name__ == "__main__":
    unittest.main()
