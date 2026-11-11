"""No unsafe auto-correction of commercial facts."""
import unittest
from Quotation_KEKOREA.orchestration.workflows.label_typos import canonical_label, normalize_trade_labels


class LabelTypoTests(unittest.TestCase):
    def test_explicit_label_typo_examples(self):
        for label, expected in (
            ("buyr", "buyer"), ("byuer", "buyer"), ("seler", "seller"),
            ("quantiy", "quantity"), ("unit prce", "unit_price"),
            ("paymnt terms", "payment_terms"), ("curreny", "currency"),
            ("prodcut", "product"), ("구매자", "buyer"), ("판매자", "seller"),
        ):
            with self.subTest(label=label):
                self.assertEqual(canonical_label(label), expected)

    def test_only_labels_rewritten(self):
        source = "Buyr: TENGYAO TECHNOLOGY CO LTD\\nSeler = KE KOREA\\nQuantiy: 1,000,000\\nUnit Prce: USD 0.225"
        normalized = normalize_trade_labels(source)
        self.assertIn("buyer: TENGYAO TECHNOLOGY CO LTD", normalized)
        self.assertIn("seller = KE KOREA", normalized)
        self.assertIn("quantity: 1,000,000", normalized)
        self.assertIn("unit_price: USD 0.225", normalized)

    def test_do_not_change_values_or_ambiguous_short_tokens(self):
        for value in ("BUYR TECHNOLOGY CO LTD", "Buyer is buyr company", "PI: 123", "Rate: 0.225", "EXW: Jincheon"):
            self.assertEqual(normalize_trade_labels(value), value)
        self.assertIsNone(canonical_label("prce"))

    def test_no_arbitrary_typo_rewriting(self):
        self.assertEqual(normalize_trade_labels("buyer: seler\\nprice: 0.225"), "buyer: seler\\nprice: 0.225")


if __name__ == "__main__":
    unittest.main()
