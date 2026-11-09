import unittest
from Quotation_KEKOREA.contracts.contract_versions import _numbers, _normalize_month_words


class ContractTranslationMonthTests(unittest.TestCase):
    def test_korean_dates_equal_english_month_names(self):
        korean = '계약기간은 2026년 11월 10일부터 3년으로 하며, 종료일은 2029년 11월 10일로 한다. 30일.'
        english = 'The term shall be 3 years from November 10, 2026, ending November 10, 2029. 30 days.'
        self.assertEqual(_numbers(korean), _numbers(english))

    def test_actual_month_change_is_detected(self):
        self.assertNotEqual(_numbers('2026년 11월 10일'), _numbers('December 10, 2026'))
        self.assertNotEqual(_numbers('2026년 11월 10일'), _numbers('November 11, 2026'))

    def test_actual_amount_or_percent_change_is_detected(self):
        self.assertNotEqual(_numbers('30%'), _numbers('40%'))
        self.assertNotEqual(_numbers('USD 1,000'), _numbers('USD 1100'))

    def test_month_abbreviations_and_british_dates(self):
        self.assertEqual(_numbers('2026년 11월 10일'), _numbers('10 Nov. 2026'))
        self.assertEqual(_numbers('2026년 5월 10일'), _numbers('May 10, 2026'))

    def test_modal_may_is_not_misread_as_month(self):
        self.assertEqual(_normalize_month_words('The party may terminate within 30 days.'),
                         'The party may terminate within 30 days.')


if __name__ == '__main__':
    unittest.main()
