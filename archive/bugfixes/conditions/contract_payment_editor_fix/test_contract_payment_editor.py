"""Regression coverage: user-editable payment terms must change generated clauses.
Copy to Quotation_KEKOREA/tests/ after patching.
"""
import unittest
from Quotation_KEKOREA.contracts.commission_policy import (
    apply_payment_policy, payment_policy_issues,
)


def example_snapshot(language='ko', *, custom=True):
    terms = [
        {'key': 'currency', 'value': 'USD', 'status': 'confirmed'},
        {'key': 'payment_trigger', 'value': 'actual receipt of investment funds', 'status': 'confirmed'},
    ]
    if custom:
        terms.extend([
            {'key': 'payment_deadline', 'value': 'D+14 calendar days', 'status': 'confirmed'},
            {'key': 'late_interest_rate', 'value': '6%', 'status': 'confirmed'},
        ])
    return {
        'contract_id': 'test-contract', 'revision': 1,
        'contract_type': 'investment_commission', 'language': language,
        'parties': [
            {'roles': ['commission_payer'], 'legal_name': 'VIBE INVESTMENT PTE LTD',
             'country': 'Singapore', 'status': 'confirmed'},
            {'roles': ['fundraiser'], 'legal_name': 'KE KOREA CO. LTD',
             'country': 'South Korea', 'status': 'confirmed'},
        ],
        'terms': terms, 'clauses': [], 'issues': [],
    }


class PaymentEditorContractTests(unittest.TestCase):
    def _payment_text(self, snapshot):
        output = apply_payment_policy(snapshot, env={})
        texts = {x['id']: x['sentences'][0]['text'] for x in output['clauses']
                 if x['id'].startswith('commission_payment_')}
        return output, texts

    def test_korean_custom_deadline_and_interest_are_used(self):
        output, texts = self._payment_text(example_snapshot())
        self.assertIn('14일 이내(D+14', texts['commission_payment_0'])
        self.assertIn('연 6%', texts['commission_payment_2'])
        self.assertNotIn('법적 적용 가능성을', texts['commission_payment_0'])
        self.assertIn('서명 전 검토', texts['commission_payment_2'])
        self.assertIn('수취 계좌 확인 필요', texts['commission_payment_1'])
        self.assertEqual(next(t['value'] for t in output['terms'] if t['key'] == 'payment_deadline'),
                         'D+14 calendar days')

    def test_english_custom_deadline_and_interest_are_used(self):
        _, texts = self._payment_text(example_snapshot('en'))
        self.assertIn('within 14 calendar days', texts['commission_payment_0'])
        self.assertIn('6% per annum', texts['commission_payment_2'])
        self.assertIn('legal validity', texts['commission_payment_2'])

    def test_default_seven_days_is_unchanged_without_custom_terms(self):
        _, texts = self._payment_text(example_snapshot(custom=False))
        self.assertIn('7일 이내(D+7', texts['commission_payment_0'])
        self.assertNotIn('연 6%', texts['commission_payment_2'])

    def test_unverified_account_and_legal_review_remain_flags(self):
        output, _ = self._payment_text(example_snapshot())
        notices = [x['message'] for x in payment_policy_issues(output, env={})]
        self.assertTrue(any('계좌' in message for message in notices))
        self.assertTrue(any('연체이율' in message for message in notices))


if __name__ == '__main__':
    unittest.main()
