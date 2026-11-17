"""Master/public app share the trade discount parser: payment % is not a sale discount."""
import unittest
from Quotation_KEKOREA.agent.document_engine import _discount_instruction


class SharedDiscountPaymentGuardTests(unittest.TestCase):
    def test_screenshot_0_discount_30_70_payment_and_model_change(self):
        prompt = (
            "구매 단가: 첨부 파일 USD 단가를 적용, 추가 할인율은 0%입니다.\n"
            "결제조건: T/T 계약금 30%, 잔금 70%는 선적 전 지급.\n"
            "제품 모델 변경이나 대체품 공급은 사전 협의.")
        self.assertEqual(_discount_instruction(prompt), ("0", None))

    def test_unlabeled_payment_percent_never_becomes_discount(self):
        prompt = "T/T 30% deposit, 70% balance. Additional discount rate: 5%."
        self.assertEqual(_discount_instruction(prompt), ("5", None))

    def test_real_discount_correction_keeps_rate_but_unrelated_model_change_does_not(self):
        self.assertEqual(_discount_instruction("할인율 10%에서 5%로 변경; 잔금 70%."), ("5", None))
        self.assertEqual(_discount_instruction("70% 할인. 선금 30%, 잔금 70%. 모델 변경 사전 협의"), ("70", None))


    def test_fortynine_item_pi_keeps_base_usd_price_instead_of_halving_or_discounting(self):
        """Simulates the screenshot with 49 imported rows and an incorrect 70% AI discount."""
        from unittest.mock import patch
        from Quotation_KEKOREA.agent.document_engine import finalize_extracted_trade
        from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate

        prompt = (
            "제품 가격: 첨부 USD 단가 적용, 추가 할인율은 0%입니다.\n"
            "결제조건: T/T 계약금 30%, 잔금 70% 선적 전 지급.\n"
            "제품 모델 변경은 사전 협의.")
        source = {
            "document_type": "PI", "product_family": "other", "currency": "USD",
            "seller": {"legal_name": "KE KOREA CO LTD", "address": "Seoul, Korea"},
            "buyer": {"legal_name": "Synthetic Buyer Ltd", "address": "Singapore"},
            "document_number": "DRAFT",
            "incoterms": "CIF Singapore Port, Singapore (Incoterms 2020)",
            "payment_terms": "T/T deposit 30%; balance 70% before shipment",
            "items": [{
                "product_name": f"Synthetic Laptop {i:02d}", "quantity": "300",
                "paid_quantity": "300", "unit": "PCS", "unit_price": "1270",
                "price_basis": "PCS", "discount_percent": "70",
                "free_quantity": "0", "shipped_quantity": "300",
                "source": f"Synthetic Laptop {i:02d} 300 PCS USD 1270",
            } for i in range(1, 50)],
            "conflicts": [], "missing_fields": [], "source_notes": [],
        }
        # This test is about discount intent, not optical extraction accuracy.
        with patch("Quotation_KEKOREA.agent.document_engine.verify_item_quotes",
                   side_effect=lambda draft, instruction, image_context=False: draft):
            document = finalize_extracted_trade(
                source, prompt, "PI", (),
                {"products": [], "purchase_prices": [], "buyer_prices": []})
        self.assertEqual(len(document["items"]), 49)
        self.assertEqual(document["payment_terms"], source["payment_terms"])
        self.assertTrue(all(x["discount_percent"] == "0" for x in document["items"]))
        self.assertTrue(all(x["unit_price"] == "1270" for x in document["items"]))
        calculated = validate_and_calculate(document)
        self.assertEqual(calculated["items"][0]["final_unit_price"], "1270")
        self.assertEqual(calculated["items"][0]["line_total"], "381000.00")
        self.assertEqual(calculated["total"], "18669000.00")


if __name__ == "__main__":
    unittest.main()
