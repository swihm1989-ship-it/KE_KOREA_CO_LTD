"""Contract chat reply language must follow the newest user message, not document language."""
import json
import unittest
from Quotation_KEKOREA.contracts.service import analyze_trade, conversation_response_language
from Quotation_KEKOREA.tests.test_contract_service import FakeResponse


class ContractLanguagePolicyTests(unittest.TestCase):
    def test_language_detector(self):
        samples = {
            '계약서 커미션 3%': 'ko',
            'Commission 3%, 한국 계약서': 'ko',
            'Can you draft the commission agreement?': 'en',
            'USD 1,760만불': 'ko',
            '': 'ko',
        }
        for prompt, expected in samples.items():
            with self.subTest(prompt=prompt):
                self.assertEqual(conversation_response_language(prompt), expected)

    def test_analysis_instruction_is_separate_from_document_language(self):
        response = {'contract_type': 'sale', 'parties': [], 'terms': [], 'questions': [], 'issues': []}
        for prompt, expected_language, doc_language in (
            ('안녕하세요. Commission 3% 계약', 'ko', 'en'),
            ('What are the payment terms?', 'en', 'ko'),
        ):
            with self.subTest(prompt=prompt):
                captured = {}
                def fake_open(request, timeout):
                    captured['payload'] = json.loads(request.data.decode('utf-8'))
                    return FakeResponse(response)
                analyze_trade([{'role': 'user', 'content': prompt}],
                              {'revision': 1, 'language': doc_language}, [],
                              env={'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test'},
                              client=fake_open)
                payload = captured['payload']
                submitted = json.loads(payload['input'][0]['content'])
                self.assertEqual(submitted['conversation_response_language'], expected_language)
                self.assertIn('conversation_response_language', payload['instructions'])

if __name__ == '__main__':
    unittest.main()
