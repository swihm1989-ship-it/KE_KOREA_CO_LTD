import unittest
from Quotation_KEKOREA.contracts.clause_terms import clause_evidence, merge_clause_candidates


class ClauseTermBridgeTests(unittest.TestCase):
    def snapshot(self):
        return {'contract_type': 'sale', 'contract_id': 'sample', 'revision': 1, 'language': 'ko',
                'clauses': [{'title': '물품', 'sentences': [{'id': 's1', 'text': '월 물량은 50,000KG로 한다.', 'term_ids': ['quantity']}]}],
                'terms': [{'key': 'unit_price', 'value': '4', 'status': 'confirmed', 'currency': 'USD'}], 'parties': []}

    def test_candidate_reuses_text_without_certifying(self):
        original = self.snapshot()
        analysis = {'terms': [{'key': 'quantity', 'value': '50,000', 'unit': 'KG'},
                              {'key': 'unit_price', 'value': '7', 'currency': 'USD'}],
                    'parties': [{'roles': ['buyer'], 'legal_name': 'OCI Co. Ltd.'}]}
        candidate = merge_clause_candidates(original, analysis)
        self.assertEqual(candidate['terms'][0]['value'], '4')
        self.assertEqual(candidate['terms'][0]['status'], 'confirmed')
        self.assertEqual(candidate['terms'][1]['value'], '50,000')
        self.assertEqual(candidate['terms'][1]['status'], 'suggested')
        self.assertEqual(candidate['parties'][0]['status'], 'suggested')
        self.assertEqual(original['parties'], [])
        self.assertIn('50,000KG', clause_evidence(original))

    def test_preserve_existing_party_values_and_downgrade_if_fill_blank(self):
        original = self.snapshot()
        original['parties'] = [{'roles': ['buyer'], 'legal_name': 'OCI Co. Ltd.',
                                'country': None, 'address': None, 'status': 'confirmed'}]
        candidate = merge_clause_candidates(original, {'terms': [], 'parties': [
            {'roles': ['buyer'], 'legal_name': 'Different Co', 'country': 'KR'}]})
        self.assertEqual(candidate['parties'][0]['legal_name'], 'OCI Co. Ltd.')
        self.assertEqual(candidate['parties'][0]['country'], 'KR')
        self.assertEqual(candidate['parties'][0]['status'], 'suggested')

    def test_draft_does_not_mark_every_sentence(self):
        from Quotation_KEKOREA.contracts.draft_exports import export_draft
        snap = self.snapshot()
        snap['title'] = 'Supply'
        snap['terms'].append({'key': 'quantity', 'value': '50,000', 'status': 'confirmed'})
        snap['clauses'][0]['sentences'].append({'id': 's2', 'text': '계약일은 추후 정한다.', 'term_ids': ['contract_date']})
        result = export_draft(snap, formats=('docx',))
        from docx import Document
        from io import BytesIO
        doc = Document(BytesIO(result['docx']['content']))
        paragraphs = [p.text for p in doc.paragraphs]
        self.assertIn('월 물량은 50,000KG로 한다.', paragraphs)
        self.assertIn('계약일은 추후 정한다.', paragraphs)
        self.assertNotIn('[확인 필요] 계약일은 추후 정한다.', paragraphs)
        self.assertNotIn('[확인 필요] 월 물량은 50,000KG로 한다.', paragraphs)


if __name__ == '__main__':
    unittest.main()
