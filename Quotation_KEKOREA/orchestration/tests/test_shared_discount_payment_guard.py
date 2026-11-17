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


if __name__ == "__main__":
    unittest.main()
