"""Regression: payment installments must never become trade price discounts.

Source example: 2026-11-17 KE KOREA Lenovo computer-parts PI.
"""
import unittest
from copy import deepcopy
from unittest.mock import patch

from Quotation_KEKOREA.agent.document_engine import (
    _discount_instruction, finalize_extracted_trade,
)
from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate


SOURCE_PROMPT = """발주 품목 및 수량: 첨부 엑셀 파일에 기재된 전체 제품과 수량을 기준으로 합니다.
모델번호, 색상 및 세부 사양은 첨부 목록과 동일하게 적용해 주세요.
구매 단가: 첨부 파일의 USD 단가를 적용하며, 추가 할인율은 0%입니다.
인도조건: CIF Singapore Port, Singapore (Incoterms 2020).
결제조건: T/T 계약금 30%, 잔금 70%는 선적 전 지급합니다.
선적 일정: 계약금 수령 후 30일 이내 선적을 요청합니다.
제품 상태: 정품 신품 및 미개봉 상태로 공급해 주시고, 모델 변경이나
대체품 공급은 사전 협의해 주세요.
"""


class PaymentTermsNotDiscountTests(unittest.TestCase):
    def test_actual_korean_order_discounts_zero_not_payment_balance_seventy(self):
        self.assertEqual(_discount_instruction(SOURCE_PROMPT), ("0", None))

    def test_short_korean_payment_and_discount_in_one_sentence(self):
        prompt = "추가 할인율은 0%, 결제조건은 계약금 30%, 잔금 70%입니다."
        self.assertEqual(_discount_instruction(prompt), ("0", None))

    def test_payment_first_and_english_discount_five(self):
        text = "T/T 30% deposit and 70% balance before shipment. Additional discount: 5%."
        self.assertEqual(_discount_instruction(text), ("5", None))

    def test_genuine_seventy_percent_discount_is_not_silenced(self):
        text = "Price: USD 1,270 per piece. Apply 70% discount. T/T 30% deposit, 70% balance."
        self.assertEqual(_discount_instruction(text), ("70", None))

    def test_vague_discount_and_payment_70_requires_discount_confirmation(self):
        value, issue = _discount_instruction(
            "Discount rate to be confirmed. Payment: 30% deposit and 70% balance.")
        self.assertIsNone(value)
        self.assertIn("Discount was mentioned", issue)

    def test_two_genuine_discount_rates_do_not_get_overridden_by_unrelated_model_change(self):
        value, issue = _discount_instruction(
            "제품 할인가 10%, 추가 할인율 5%; 계약금 30%, 잔금 70%. 모델 변경 사전 협의")
        self.assertIsNone(value)
        self.assertIn("Multiple discount rates", issue)

    def test_legitimate_discount_correction_keeps_last_rate(self):
        self.assertEqual(_discount_instruction(
            "할인율 10%에서 5%로 수정합니다. 결제조건 T/T 계약금 30%, 잔금 70%."),
            ("5", None))

    def test_no_discount_reference_payment_alone_is_full_price(self):
        self.assertEqual(_discount_instruction(
            "결제조건: T/T 계약금 30%, 잔금 70%는 선적 전 지급"), ("0", None))

    def test_public_pi_49_items_keep_original_unit_prices_and_calculate_without_payment_discount(self):
        """Wrong 70% caused a 49-line PI to show prices at only 30% of source."""
        draft = {
            "document_type": "PI", "product_family": "other", "currency": "USD",
            "seller": {"legal_name": "KE KOREA CO LTD", "address": "1 Example St"},
            "buyer": {"legal_name": "SYNTHETIC BUYER LTD", "address": "2 Example St"},
            "incoterms": "CIF Singapore Port, Singapore (Incoterms 2020)",
            "payment_terms": "T/T 30% deposit, 70% balance before shipment",
            "items": [{
                "product_name": f"Synthetic Notebook Model {i:02d}",
                "quantity": "300", "paid_quantity": "300", "unit": "PCS",
                "unit_price": "381", "price_basis": "PCS",
                "discount_percent": "70", "free_quantity": "0",
                "shipped_quantity": "300", "source": f"Model {i:02d}: 300 PCS USD 381",
            } for i in range(1, 50)],
            "missing_fields": [], "conflicts": [], "source_notes": [],
        }
        with patch("Quotation_KEKOREA.agent.document_engine.verify_item_quotes",
                   side_effect=lambda draft, prompt, image_context=False: draft):
            checked = finalize_extracted_trade(deepcopy(draft), SOURCE_PROMPT, "PI", (),
                                               {"products": [], "buyer_prices": [],
                                                "purchase_prices": []}, ())
        self.assertEqual(checked["payment_terms"], draft["payment_terms"])
        self.assertTrue(all(x["discount_percent"] == "0" for x in checked["items"]))
        self.assertTrue(all(x["unit_price"] == "381" for x in checked["items"]))
        calculated = validate_and_calculate(checked)
        self.assertEqual(calculated["items"][0]["final_unit_price"], "381.00")
        self.assertEqual(calculated["items"][0]["line_total"], "114300.00")
        self.assertEqual(calculated["total"], "5600700.00")


if __name__ == "__main__":
    unittest.main()
