"""Sales contract opening clause must be deterministic and revision-safe."""
from copy import deepcopy
import unittest

from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.sale_scope_template import (
    sale_scope_clause, apply_sale_scope_template,
)
from Quotation_KEKOREA.contracts.editing import propose_sentence_deletion, apply_proposal
from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys


def fixture():
    snapshot = new_snapshot('sale-fixture', 'sale', 'ko')
    snapshot['title'] = '태양광 셀 공급계약'
    snapshot['parties'] = [
        {'legal_name': 'KE KOREA CO. LTD', 'address': '대한민국 양평로 157',
         'representative': 'SEOKWON IHM', 'representative_title': '대표이사',
         'roles': ['seller']},
        {'legal_name': 'TENGYAO TECHNOLOGY CO. LTD',
         'address': 'WUXI ECONOMIC FREE ZONE UNIT 7, ROC CHINA',
         'representative': 'ALEX', 'representative_title': '대표이사',
         'roles': ['buyer']},
    ]
    snapshot['terms'] = [
        {'id': 'brand', 'key': 'brand', 'value': '한화솔루션',
         'status': 'confirmed'},
        {'id': 'goods', 'key': 'products', 'value': '한화 등외급 태양광 셀',
         'status': 'confirmed'},
        {'id': 'quantity', 'key': 'quantity', 'value': '2,324,938',
         'unit': '장', 'status': 'confirmed'},
        {'id': 'price', 'key': 'unit_price', 'value': '0.225',
         'currency': 'USD', 'unit': '장', 'status': 'confirmed'},
        {'id': 'delivery', 'key': 'delivery', 'value': 'EXW 한화솔루션 진천공장',
         'status': 'confirmed'},
        {'id': 'payment', 'key': 'payment_trigger',
         'value': '낙찰 즉시 계약금 10%, 낙찰일로부터 7일 후 잔금 90%',
         'status': 'confirmed'},
    ]
    return snapshot


class SaleScopeTemplateTests(unittest.TestCase):
    def test_party_scope_rows_use_exact_saved_values_not_example_prepayment(self):
        snapshot = fixture()
        before = deepcopy(snapshot)
        clause = sale_scope_clause(snapshot)
        self.assertEqual(snapshot, before)
        self.assertEqual(clause['topic_key'], 'scope')
        self.assertEqual(clause['title'], '당사자 및 거래 범위')
        lines = [s['text'] for s in clause['sentences']]
        self.assertIn('이 계약의 당사자는 공급자 KE KOREA CO. LTD', lines[0])
        self.assertIn('대표자: ALEX, 대표이사', lines[0])
        self.assertIn('브랜드: 한화솔루션', lines)
        self.assertIn('제품: 한화 등외급 태양광 셀 2,324,938 장', lines)
        self.assertIn('가격: USD 0.225/장', lines)
        self.assertIn('인도조건: EXW 한화솔루션 진천공장', lines)
        self.assertIn('결제조건: 낙찰 즉시 계약금 10%, 낙찰일로부터 7일 후 잔금 90%', lines)
        self.assertNotIn('TT 100% in Advance', '\\n'.join(lines))
        self.assertEqual(
            next(s for s in clause['sentences'] if s.get('sale_spec_field') == 'unit_price')['term_ids'],
            ['price'],
        )

    def test_unconfirmed_term_is_flagged_and_missing_values_stay_empty(self):
        snapshot = fixture()
        snapshot['terms'] = [t for t in snapshot['terms']
                             if t['key'] not in ('brand', 'delivery')]
        price = next(t for t in snapshot['terms'] if t['key'] == 'unit_price')
        price['status'] = 'suggested'
        clause = sale_scope_clause(snapshot)
        lines = [s['text'] for s in clause['sentences']]
        self.assertIn('브랜드: ', lines)
        self.assertIn('인도조건: ', lines)
        self.assertTrue(any('제안(미확정)' in line and '0.225' in line for line in lines))

    def test_inserts_fixed_scope_but_preserves_unrelated_liability_clause(self):
        snapshot = fixture()
        snapshot['clauses'] = [
            {'id': 'old_scope', 'title': '당사자 및 거래 범위', 'topic_key': 'scope',
             'order': 1, 'sentences': [
                 {'id': 'old_scope_sentence', 'text': 'AI prose, not fixed template.'}]},
            {'id': 'liability', 'title': '손해배상', 'topic_key': 'liability',
             'order': 2, 'sentences': [
                 {'id': 'liability_s1', 'text': '상대방의 손해를 배상한다.'}]},
        ]
        old = deepcopy(snapshot)
        updated = apply_sale_scope_template(snapshot)
        self.assertEqual(snapshot, old)
        self.assertEqual(updated['clauses'][0]['id'], 'old_scope')
        self.assertEqual(updated['clauses'][1], old['clauses'][1])
        self.assertEqual(updated['clauses'][0]['sentences'][2]['sale_spec_field'], 'brand')
        self.assertEqual(apply_sale_scope_template(snapshot, repair_context={'draft': snapshot}),
                         snapshot)

    def test_audit_repair_cannot_erase_fixed_sale_trade_values(self):
        before = apply_sale_scope_template(fixture())
        corrupted = deepcopy(before)
        corrupted['clauses'][0]['sentences'][4]['text'] = '가격: USD 0.1/장'
        result = apply_sale_scope_template(
            corrupted, repair_context={'draft': before, 'editable_clause_ids': [
                before['clauses'][0]['id'],
            ]})
        self.assertEqual(result['clauses'][0], before['clauses'][0])
        self.assertNotIn('0.1/장', '\\n'.join(
            s['text'] for s in result['clauses'][0]['sentences']))
        self.assertEqual(corrupted['clauses'][0]['sentences'][4]['text'], '가격: USD 0.1/장')

    def test_english_template_translates_labels_and_titles_not_commercial_values(self):
        snapshot = fixture()
        snapshot['language'] = 'en'
        clause = sale_scope_clause(snapshot)
        lines = [sentence['text'] for sentence in clause['sentences']]
        self.assertEqual(clause['title'], 'Parties and Scope of Sale')
        self.assertIn('Representative: ALEX, Chief Executive Officer', lines[0])
        self.assertIn('Brand: 한화솔루션', lines)
        self.assertIn('Delivery Terms: EXW 한화솔루션 진천공장', lines)
        self.assertTrue(any(line.startswith('Payment Terms:') for line in lines))

    def test_commission_contract_and_missing_party_are_not_changed(self):
        snap = fixture()
        snap['contract_type'] = 'trade_commission'
        self.assertIsNone(sale_scope_clause(snap))
        snap['contract_type'] = 'sale'
        snap['parties'].pop()
        self.assertIsNone(sale_scope_clause(snap))
        self.assertEqual(apply_sale_scope_template(snap), snap)

    def test_sale_row_can_be_removed_through_existing_revision_engine(self):
        snapshot = apply_sale_scope_template(fixture())
        row = next(s for s in snapshot['clauses'][0]['sentences']
                   if s.get('sale_spec_field') == 'brand')
        proposal = propose_sentence_deletion(snapshot, row['id'])
        self.assertEqual(len(snapshot['clauses'][0]['sentences']), 8)
        revised = apply_proposal(snapshot, proposal, [proposal['changes'][0]['id']])
        self.assertEqual(revised['revision'], 2)
        self.assertFalse(any(s.get('sale_spec_field') == 'brand'
                             for s in revised['clauses'][0]['sentences']))

    def test_brand_alias_is_normalized(self):
        data, warnings = normalize_term_keys({
            'terms': [{'key': '브랜드명', 'value': '한화솔루션', 'status': 'suggested'}]})
        self.assertEqual(data['terms'][0]['key'], 'brand')
        self.assertEqual(warnings, [])


if __name__ == '__main__':
    unittest.main()
