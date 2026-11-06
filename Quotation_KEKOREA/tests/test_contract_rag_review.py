"""Tests for safe contract RAG review response validation."""
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.review import review_contract

SNAPSHOT = {'contract_type': 'trade_commission', 'language': 'ko', 'clauses': [
    {'title': 'Commission', 'sentences': [{'id': 's1', 'text': 'Fee is 3%.'},
                                       {'id': 's2', 'text': 'Payment follows receipt.'}]}
]}
SOURCES = [{'id': 'sample1', 'title': 'Reviewed precedent', 'text': 'Payment within 7 days', 'locator': 'Article 3'}]
FINDING = {'severity': 'high', 'title': '지급기한', 'reason': '기한 누락',
           'suggestion': '7일 이내로 명시', 'sentence_id': 's2', 'source_ids': ['sample1']}


class ContractRagReviewTests(unittest.TestCase):
    def test_valid_result_has_source_and_sentence(self):
        with patch('Quotation_KEKOREA.contracts.review._call', return_value={'findings': [FINDING]}):
            result = review_contract(SNAPSHOT, SOURCES, env={'OPENAI_API_KEY': 'test'})
        self.assertEqual(result[0]['source_ids'], ['sample1'])
        self.assertEqual(result[0]['sentence_id'], 's2')

    def test_unverified_citation_is_rejected(self):
        wrong = dict(FINDING, source_ids=['made_up'])
        with patch('Quotation_KEKOREA.contracts.review._call', return_value={'findings': [wrong]}):
            with self.assertRaisesRegex(ValueError, '출처'):
                review_contract(SNAPSHOT, SOURCES, env={})

    def test_unrecognized_sentence_is_rejected(self):
        wrong = dict(FINDING, sentence_id='invented')
        with patch('Quotation_KEKOREA.contracts.review._call', return_value={'findings': [wrong]}):
            with self.assertRaisesRegex(ValueError, '문장'):
                review_contract(SNAPSHOT, SOURCES, env={})

    def test_highest_risk_first_deduplicated_and_limited(self):
        many = [dict(FINDING, sentence_id='s1', severity='low'),
                dict(FINDING, sentence_id='s1', severity='high'),
                dict(FINDING, sentence_id='s2', severity='medium')]
        with patch('Quotation_KEKOREA.contracts.review._call', return_value={'findings': many}):
            result = review_contract(SNAPSHOT, SOURCES, env={})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['severity'], 'high')

    def test_empty_contract_refused(self):
        with self.assertRaisesRegex(ValueError, '초안'):
            review_contract({'clauses': []}, [], env={})


if __name__ == '__main__':
    unittest.main()
