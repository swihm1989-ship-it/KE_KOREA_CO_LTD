"""Cross-category MASTER document safety and amount integrity: synthetic only."""
from decimal import Decimal
import unittest

from Quotation_KEKOREA.orchestration.workflows.ai_intake import make_trade_candidate
from Quotation_KEKOREA.orchestration.workflows.commercial_values import apply_bulk_discount


def analysis(rows, currency="USD"):
    terms = [{"key": key, "value": value, "status": "suggested", "source_refs": []}
             for name, qty, price, unit in rows
             for key, value in (("products", name), ("quantity", str(qty)),
                                ("unit_price", str(price)), ("unit", unit))]
    terms += [
        {"key": "currency", "value": currency, "status": "suggested", "source_refs": []},
        {"key": "payment_trigger", "value": "30% deposit; 70% balance", "status": "suggested", "source_refs": []},
    ]
    return {"contract_type": "sale",
            "parties": [{"roles": ["buyer"], "legal_name": "SYNTHETIC BUYER", "source_refs": []},
                        {"roles": ["seller"], "legal_name": "SYNTHETIC SELLER", "source_refs": []}],
            "terms": terms, "questions": [], "issues": []}


SCENARIOS = [
    ("computer_peripherals", "other", "USD",
     [("Wireless Mouse MX2", 10, "12.50", "PCS"), ("Keyboard K3", 8, "25.00", "PCS"),
      ("USB Drive 64GB", 15, "9.90", "PCS")], "473.50"),
    ("industrial_pumps", "other", "USD",
     [("Pump P100", 3, "920.00", "PCS"), ("Valve V20", 20, "12.25", "PCS"),
      ("Filter F1", 7, "34.50", "PCS")], "3246.50"),
    ("copper", "other", "USD",
     [("Copper Tube CU-001", 10, "15.50", "KG"), ("Copper Rod CR-002", 20, "9.50", "KG"),
      ("Copper Sheet CS-003", 15, "12.20", "KG")], "528.00"),
    ("oil_related", "other", "USD",
     [("Industrial Lubricant L-1", 12, "35.00", "PCS"), ("Hydraulic Fluid H2", 8, "75.00", "PCS"),
      ("Oil Filter O3", 25, "8.00", "PCS")], "1220.00"),
    ("semiconductor", "other", "USD",
     [("HBM3 Test Unit", 2, "150.00", "PCS"), ("Memory Test Module", 9, "80.00", "PCS"),
      ("Connector CN-3", 20, "3.50", "PCS")], "1090.00"),
    ("food_service", "other", "KRW",
     [("Coffee Beans", 100, "17000", "KG"), ("Paper Cups", 500, "150", "PCS"),
      ("Lids", 500, "85", "PCS")], "1817500"),
    ("solar_module", "solar_module", "USD",
     [("Module A", 10, "60.00", "PCS"), ("Module B", 20, "45.00", "PCS"),
      ("Module C", 15, "30.00", "PCS")], "1950.00"),
    ("cosmetics", "cosmetics", "KRW",
     [("Exo Clinica UV Suncream", 2, "5640", "PCS"),
      ("Azulene Cure Solution Ampoule", 3, "5910", "PCS"),
      ("Exo Clinica Gel", 1, "8360", "PCS")], "37370"),
]


class CrossCategoryQATests(unittest.TestCase):
    def test_eight_product_families_keep_every_row_price_quantity_and_total(self):
        for scenario, family, currency, rows, expected in SCENARIOS:
            for kind in ("PI", "PO", "CI", "PL"):
                with self.subTest(scenario=scenario, kind=kind):
                    output = make_trade_candidate(kind, analysis(rows, currency),
                                                  product_family=family)
                    self.assertEqual(len(output["items"]), len(rows))
                    self.assertEqual([r["product_name"] for r in output["items"]],
                                     [r[0] for r in rows])
                    self.assertEqual([r["quantity"] for r in output["items"]],
                                     [str(r[1]) for r in rows])
                    self.assertEqual([r["unit_price"] for r in output["items"]],
                                     [str(r[2]) for r in rows])
                    self.assertEqual([r["unit"] for r in output["items"]],
                                     [r[3] for r in rows])
                    total = sum(Decimal(r["quantity"]) * Decimal(r["unit_price"])
                                for r in output["items"])
                    self.assertEqual(total, Decimal(expected))
                    self.assertEqual(output["payment_terms"], "30% deposit; 70% balance")
                    self.assertEqual(output["currency"], currency)

    def test_five_percent_is_a_discount_not_seventy_percent_balance(self):
        scenario, family, currency, rows, expected = SCENARIOS[0]
        candidate = make_trade_candidate("PI", analysis(rows), product_family=family)
        revised = apply_bulk_discount({"PI": candidate}, "PI", "5")["PI"]
        self.assertEqual([r["discount_percent"] for r in revised["items"]], ["5"] * 3)
        self.assertEqual(revised["payment_terms"], "30% deposit; 70% balance")
        net = sum(Decimal(r["quantity"]) * Decimal(r["unit_price"])
                  * (Decimal("100") - Decimal(r["discount_percent"])) / Decimal("100")
                  for r in revised["items"])
        self.assertEqual(net, Decimal("449.825"))

    def test_missing_price_in_noncosmetic_product_never_fills_with_neighbor_price(self):
        src = analysis([("Industrial Pump A", 2, "1000.00", "PCS"),
                        ("Control Unit B", 3, "125.00", "PCS"),
                        ("Pressure Sensor C", 5, "15.00", "PCS")])
        src["terms"] = [t for t in src["terms"] if not
                        (t["key"] == "unit_price" and t["value"] == "125.00")]
        candidate = make_trade_candidate("PI", src, product_family="other")
        self.assertEqual(len(candidate["items"]), 3)
        self.assertEqual([r["unit_price"] for r in candidate["items"]], ["", "", ""])
        self.assertTrue(all(not r["price_source"] for r in candidate["items"]))


if __name__ == "__main__":
    unittest.main()
