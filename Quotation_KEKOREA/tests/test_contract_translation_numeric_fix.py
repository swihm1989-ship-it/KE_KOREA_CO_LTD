"""Numeric-value invariants for translated Korean/English contract segments."""
import unittest

from Quotation_KEKOREA.contracts.contract_versions import _numbers, translate_contract
from Quotation_KEKOREA.tests.test_contract_versions import ContractVersionTests


class TranslationNumericFixTests(unittest.TestCase):
    def test_hangul_adjacent_numbers_are_detected(self):
        self.assertEqual(_numbers('계약금의30%는 7일 이내, 1,000USD 지급'),
                         _numbers('30 % of the deposit is due within 7 days, USD 1000.00'))

    def test_product_codes_not_treated_as_quantities(self):
        self.assertEqual(_numbers('M10, 제품명 X12, 12PCS'), ['12'])

    def test_repeated_amounts_preserved(self):
        self.assertNotEqual(_numbers('USD 5 + USD 5'), _numbers('USD 5'))

    def test_changed_percentage_is_not_equal(self):
        self.assertNotEqual(_numbers('계약금의30%'), _numbers('30 of deposit'))

    def test_changed_deadline_is_rejected_with_clauses_shown(self):
        source = ContractVersionTests().fixture()
        source['clauses'][0]['sentences'][0]['text'] = '대금의 30%를 7일 이내 지급한다.'
        def wrong(_instructions, payload, *, env):
            return {'translations': [
                {'key': s['key'], 'text': s['text'].replace('30%', '40%')}
                for s in payload['segments']
            ]}
        with self.assertRaisesRegex(ValueError, r'원문에만 있는 숫자: 30%') as captured:
            translate_contract(source, 'en', env={}, caller=wrong)
        self.assertIn('번역문에만 있는 숫자: 40%', str(captured.exception))
        self.assertIn('원문:', str(captured.exception))
        self.assertIn('번역:', str(captured.exception))
        self.assertEqual(source['language'], 'ko')

    def test_commas_and_decimal_equivalence_allowed_through_full_translation(self):
        source = ContractVersionTests().fixture()
        source['clauses'][0]['sentences'][0]['text'] = '단가 USD 1,000/KG, 30일 이내 EXW 서울 창고에서 인도.'
        def translated(_instructions, payload, *, env):
            return {'translations': [
                {'key': s['key'], 'text': s['text'].replace('USD 1,000/KG', 'USD 1000.00/KG').replace('30일', '30 days')}
                for s in payload['segments']
            ]}
        result = translate_contract(source, 'en', env={}, caller=translated)
        self.assertEqual(result['language'], 'en')
        self.assertEqual(source['language'], 'ko')


if __name__ == '__main__':
    unittest.main()
