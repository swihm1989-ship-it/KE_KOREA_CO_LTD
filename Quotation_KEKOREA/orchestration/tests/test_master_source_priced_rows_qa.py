"""Live-reproduced computer parts source recovery safety, no provider or SMTP."""
from copy import deepcopy
from decimal import Decimal
import unittest

from Quotation_KEKOREA.orchestration.workflows.source_line_items import (
    extract_explicit_priced_rows, restore_explicit_priced_rows,
)

HARDWARE = (
    "TEST ONLY. KE KOREA가 K-TECH Components에 마우스 10개(USD 12.50), "
    "키보드 8개(USD 25), USB 메모리 15개(USD 9.90)를 판매합니다. "
    "PI, CI, PL을 작성해줘. 할인 5%, 선금 30% 잔금 70%. "
    "알 수 없는 값은 빈칸으로 둬."
)


def bad_bundle(kind="PI"):
    return {
        kind: {
            "document_type": kind, "product_family": "other", "currency": "USD",
            "items": [{"product_name": "마우스, 키보드, USB 메모리",
                       "quantity": "15", "unit": "개",
                       "unit_price": "9.90", "price_source": ""}],
            "payment_terms": "선금 30% 잔금 70%",
        },
    }


class LiveSourceRecoveryTests(unittest.TestCase):
    def test_korean_three_rows_recovered_from_short_natural_prompt(self):
        parsed = extract_explicit_priced_rows(HARDWARE)
        self.assertEqual(len(parsed), 3, parsed)
        self.assertEqual([x["product_name"] for x in parsed],
                         ["마우스", "키보드", "USB 메모리"])
        self.assertEqual([x["quantity"] for x in parsed], ["10", "8", "15"])
        self.assertEqual([x["unit_price"] for x in parsed],
                         ["12.50", "25", "9.90"])
        self.assertEqual([x["unit"] for x in parsed], ["PCS"]*3)
        self.assertEqual(sum(Decimal(row["quantity"])*Decimal(row["unit_price"])
                             for row in parsed), Decimal("473.50"))

    def test_missing_products_fixed_in_all_trade_kinds(self):
        source = {k: bad_bundle(k)[k] for k in ("PI", "PO", "CI", "PL")}
        before = deepcopy(source)
        out, count = restore_explicit_priced_rows(source, HARDWARE)
        self.assertEqual(count, 3)
        for kind in ("PI", "PO", "CI", "PL"):
            self.assertEqual(len(out[kind]["items"]), 3)
            self.assertEqual(out[kind]["currency"], "USD")
            self.assertEqual(out[kind]["payment_terms"], "선금 30% 잔금 70%")
            self.assertEqual([r["unit_price"] for r in out[kind]["items"]],
                             ["12.50", "25", "9.90"])
            self.assertTrue(all(not r["price_source"] for r in out[kind]["items"]))
        self.assertEqual(source, before)

    def test_does_not_overwrite_already_separate_catalog_rows(self):
        good = {"PO": bad_bundle("PO")["PO"]}
        good["PO"]["items"] = [
            {"product_name": "Suncream", "quantity": "2", "unit_price": "5640"},
            {"product_name": "Ampoule", "quantity": "3", "unit_price": "5910"},
            {"product_name": "Gel", "quantity": "1", "unit_price": "8360"},
        ]
        original=deepcopy(good)
        outcome, count=restore_explicit_priced_rows(good, HARDWARE)
        self.assertEqual(count, 0)
        self.assertEqual(outcome, original)

    def test_nonpriced_source_never_invents_unit_prices(self):
        text=("품목: Exo Clinica UV Suncream 50g 2개, "
              "Azulene Cure Solution Ampoule 30ml 3개, "
              "Exo Clinica Gel 300ml 1개. DB 매입단가 적용.")
        self.assertEqual(extract_explicit_priced_rows(text), [])

    def test_mixed_currency_does_not_create_false_invoice_totals(self):
        text=("TEST ONLY. 마우스 10개(USD 12.50), "
              "키보드 8개(EUR 25), USB 메모리 15개(USD 9.90).")
        self.assertEqual(extract_explicit_priced_rows(text), [])
        out, count = restore_explicit_priced_rows(bad_bundle(), text)
        self.assertEqual(count, 0)
        self.assertEqual(out["PI"]["items"][0]["unit_price"], "")
        self.assertTrue(out["PI"]["missing_fields"])

    def test_missing_one_explicit_price_does_not_downgrade_to_partial_total(self):
        text=("TEST ONLY. 마우스 10개(USD 12.50), "
              "키보드 8개, USB 메모리 15개(USD 9.90).")
        self.assertEqual(extract_explicit_priced_rows(text), [])
        out, count = restore_explicit_priced_rows(bad_bundle(), text)
        self.assertEqual(count, 0)
        self.assertEqual(out["PI"]["items"][0]["unit_price"], "")

    def test_no_discounts_or_payment_percentages_are_parsed_as_product_rows(self):
        text = ("마우스 10개(USD 12.50), 키보드 8개(USD 25). "
                "선금 30%, 잔금 70%, 할인 5%.")
        rows = extract_explicit_priced_rows(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["quantity"] for r in rows], ["10","8"])

    def test_explicit_thousands_and_kg(self):
        text=("산업재: Copper Tube 1,200 KG 단가 USD 8.50; "
              "Copper Wire 2,500 KG 단가 USD 7.25")
        rows=extract_explicit_priced_rows(text)
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual([row["quantity"] for row in rows],["1200","2500"])
        self.assertEqual([row["unit"] for row in rows],["KG","KG"])


if __name__ == "__main__":
    unittest.main()
