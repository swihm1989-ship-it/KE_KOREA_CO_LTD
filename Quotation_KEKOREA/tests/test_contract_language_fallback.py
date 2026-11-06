"""Regression: English questions returned to Korean or mixed-language users must be localized."""
import json
import unittest
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.service import analyze_trade
from Quotation_KEKOREA.tests.test_contract_service import FakeResponse


class ContractLanguageFallbackTests(unittest.TestCase):
    def test_mixed_input_english_questions_get_korean_fallback(self):
        captured = []
        original = {
            'contract_type': 'investment_commission',
            'parties': [], 'terms': [],
            'questions': ['Who is the commission payer?', 'Which currency does 1760 mean?'],
            'issues': [{'code': 'party', 'severity': 'confirm', 'message': 'Confirm the payer.'}],
        }
        localized = {'translations': [
            '커미션 지급자는 누구인가요?',
            '1760의 통화는 무엇인가요?',
            '지급자를 확인해 주세요.',
        ]}
        responses = [original, localized]
        def fake_open(request, timeout):
            captured.append(json.loads(request.data))
            return FakeResponse(responses.pop(0))
        result = analyze_trade(
            [{'role': 'user', 'content': '투자자 LOTTE HOTEL, COMMISSION RATE 3%'}],
            new_snapshot('contract-1', 'investment_commission', 'en'), [],
            env={'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test'}, client=fake_open)
        self.assertEqual(result['questions'][0], '커미션 지급자는 누구인가요?')
        self.assertEqual(result['issues'][0]['message'], '지급자를 확인해 주세요.')
        self.assertEqual(result['contract_type'], 'investment_commission')
        self.assertEqual(len(captured), 2)
        second = json.loads(captured[1]['input'][0]['content'])
        self.assertEqual(second['target_language'], 'ko')

    def test_english_only_question_needs_no_translation(self):
        response = {'contract_type': 'sale', 'parties': [], 'terms': [],
                    'questions': ['Where is the property?'], 'issues': []}
        calls = []
        def fake_open(request, timeout):
            calls.append(1)
            return FakeResponse(response)
        result = analyze_trade([{'role': 'user', 'content': 'Where is the property?'}],
                               new_snapshot('contract-2', 'sale', 'ko'), [],
                               env={'OPENAI_API_KEY':'test', 'OPENAI_MODEL':'test'}, client=fake_open)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['questions'], response['questions'])

    def test_failed_translation_is_rejected(self):
        response = {'contract_type': 'sale', 'parties': [], 'terms': [],
                    'questions': ['Which currency?'], 'issues': []}
        replies = [response, {'translations': ['Which currency?']}]
        def fake_open(request, timeout):
            return FakeResponse(replies.pop(0))
        with self.assertRaisesRegex(RuntimeError, 'requested conversation language'):
            analyze_trade([{'role':'user', 'content':'달러는 무엇인가요?'}],
                          new_snapshot('contract-3', 'sale', 'en'), [],
                          env={'OPENAI_API_KEY':'test','OPENAI_MODEL':'test'}, client=fake_open)

if __name__ == '__main__':
    unittest.main()
