import unittest

from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys


class EmbeddedQuantityUnitTests(unittest.TestCase):
    def normalize(self, rows):
        return normalize_term_keys({"terms": rows})

    def test_embedded_pcs_matches_separate_pcs(self):
        result, warnings = self.normalize([
            {"key": "수량", "value": "2,324,938 PCS"},
            {"key": "quantity", "value": "2324938", "unit": "pcs"},
        ])
        self.assertEqual(len(result["terms"]), 1)
        self.assertEqual(warnings, [])
        self.assertEqual(result["terms"][0]["value"], "2,324,938 PCS")
        self.assertEqual(result["terms"][0]["status"], "suggested")

    def test_embedded_mt_matches_kg(self):
        result, warnings = self.normalize([
            {"key": "quantity", "value": "2 MT"},
            {"key": "수량", "value": "2000", "unit": "KG"},
        ])
        self.assertEqual(len(result["terms"]), 1)
        self.assertEqual(warnings, [])

    def test_different_quantities_remain_conflicts(self):
        result, warnings = self.normalize([
            {"key": "quantity", "value": "2,324,938 PCS"},
            {"key": "수량", "value": "2,324,939", "unit": "PCS"},
        ])
        self.assertEqual(len(result["terms"]), 1)
        self.assertEqual(len(warnings), 1)

    def test_unknown_unit_does_not_become_confirmed(self):
        result, warnings = self.normalize([
            {"key": "quantity", "value": "2324938"},
            {"key": "수량", "value": "2324938", "unit": "PCS"},
        ])
        self.assertEqual(len(result["terms"]), 1)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(result["terms"][0]["status"], "suggested")


if __name__ == "__main__":
    unittest.main()
