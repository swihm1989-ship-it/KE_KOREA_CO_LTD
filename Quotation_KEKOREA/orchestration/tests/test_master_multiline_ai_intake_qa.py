"""Read-only regression for real MASTER multi-item PO/PI/CI/PL input failures.

Input shapes reproduced during 2026-11-18 authenticated TinyFish QA.
All values are fictional. No network, Supabase write, PDF finalization or SMTP.
"""
from copy import deepcopy
from decimal import Decimal
import unittest

from Quotation_KEKOREA.orchestration.workflows.ai_intake import make_trade_candidate


def fake_analysis(terms):
    return {
        "contract_type": "sale",
        "parties": [
            {"roles": ["buyer"], "legal_name": "TEST BUYER", "status": "suggested"},
            {"roles": ["seller"], "legal_name": "TEST SELLER", "status": "suggested"},
        ],
        "terms": [
            {"key": key, "value": value, "status": "suggested", "source_refs": []}
            for key, value in terms
        ],
        "issues": [],
        "questions": [],
    }


class MasterMultilineExtractionQA(unittest.TestCase):
    def test_repeated_eclado_terms_produce_all_three_po_items(self):
        src=fake_analysis([
            ("products","Exo Clinica UV Suncream 00229 50g"),
            ("quantity","2"),
            ("unit_price","5640"),
            ("products","Azulene Cure Solution Ampoule 00239 30ml"),
            ("quantity","3"),
            ("unit_price","5910"),
            ("products","Exo Clinica Gel 73541 300ml"),
            ("quantity","1"),
            ("unit_price","8360"),
            ("unit","PCS"),
            ("currency","KRW"),
            ("payment_trigger","T/T 30% deposit; 70% balance"),
        ])
        before=deepcopy(src)
        for kind in ("PO","PI","CI","PL"):
            with self.subTest(kind=kind):
                doc=make_trade_candidate(kind,src,product_family="cosmetics")
                self.assertEqual(len(doc["items"]),3,doc)
                self.assertEqual([r["quantity"] for r in doc["items"]],["2","3","1"])
                self.assertEqual([r["unit_price"] for r in doc["items"]],["5640","5910","8360"])
                self.assertEqual([r["unit"] for r in doc["items"]],["PCS"]*3)
                self.assertEqual(doc["currency"],"KRW")
                self.assertEqual(sum(Decimal(r["quantity"])*Decimal(r["unit_price"]) for r in doc["items"]),Decimal("37370"))
                self.assertEqual(doc["payment_terms"],"T/T 30% deposit; 70% balance")
                self.assertTrue(all(not r["price_source"] for r in doc["items"]))
        self.assertEqual(src,before)

    def test_laptop_mouse_keyboard_usb_named_multiline_terms(self):
        src=fake_analysis([
            ("products","마우스, 키보드, USB 메모리"),
            ("quantity","마우스: 10; 키보드: 8; USB 메모리: 15"),
            ("unit_price","마우스: 12.50; 키보드: 25; USB 메모리: 9.90"),
            ("unit","개"),
            ("currency","USD"),
            ("payment_trigger","30% deposit; 70% balance"),
        ])
        for kind in ("PI","CI","PL"):
            with self.subTest(kind=kind):
                doc=make_trade_candidate(kind,src,product_family="other")
                self.assertEqual(len(doc["items"]),3)
                self.assertEqual([r["product_name"] for r in doc["items"]],["마우스","키보드","USB 메모리"])
                self.assertEqual([r["quantity"] for r in doc["items"]],["10","8","15"])
                self.assertEqual([r["unit_price"] for r in doc["items"]],["12.50","25","9.90"])
                self.assertEqual(sum(Decimal(r["quantity"])*Decimal(r["unit_price"]) for r in doc["items"]),Decimal("473.50"))
                self.assertEqual(doc["payment_terms"],"30% deposit; 70% balance")

    def test_one_price_for_three_products_is_not_copied(self):
        src=fake_analysis([
            ("products","Mouse"),("products","Keyboard"),("products","USB"),
            ("quantity","10"),("quantity","8"),("quantity","15"),
            ("unit_price","12.50"),("currency","USD"),
        ])
        doc=make_trade_candidate("PI",src,product_family="other")
        self.assertEqual(len(doc["items"]),3)
        self.assertEqual([r["unit_price"] for r in doc["items"]],["","",""])

    def test_mismatched_key_labels_are_not_mispaired(self):
        src=fake_analysis([
            ("products","Mouse, Keyboard"),
            ("quantity","Mouse: 10; Keyboard: 8"),
            ("unit_price","Keyboard: 25; Mouse: 12.50"),
            ("currency","USD"),
        ])
        doc=make_trade_candidate("PI",src,product_family="other")
        self.assertEqual(len(doc["items"]),1)
        self.assertEqual(doc["items"][0]["product_name"],"Mouse, Keyboard")
        self.assertEqual(doc["items"][0]["unit_price"],"Keyboard: 25; Mouse: 12.50")

    def test_mixed_currency_is_not_silently_accepted(self):
        src=fake_analysis([
            ("products","Mouse, Keyboard"),
            ("quantity","Mouse: 10; Keyboard: 8"),
            ("unit_price","Mouse: USD 12.5; Keyboard: EUR 25"),
            ("currency","USD"),
        ])
        doc=make_trade_candidate("PI",src,product_family="other")
        self.assertEqual(len(doc["items"]),2)
        self.assertEqual(doc["items"][0]["unit_price"],"12.5")
        self.assertEqual(doc["items"][1]["unit_price"],"")

    def test_single_item_remains_backward_compatible(self):
        doc=make_trade_candidate("PI",fake_analysis([
            ("products","USB-C Hub Model XH-100"),
            ("quantity","100"),
            ("unit","PCS"),
            ("unit_price","18.50"),
            ("currency","USD"),
        ]),product_family="other")
        self.assertEqual(len(doc["items"]),1)
        self.assertEqual(doc["items"][0]["product_name"],"USB-C Hub Model XH-100")
        self.assertEqual(doc["items"][0]["unit_price"],"18.50")


if __name__ == "__main__":
    unittest.main()
