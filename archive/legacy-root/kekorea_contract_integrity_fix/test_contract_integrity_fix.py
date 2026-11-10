"""Contract normalization / draft and final safety regression checks."""
import unittest
from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys
from Quotation_KEKOREA.contracts.rules import validate_snapshot

class IntegrityFixTests(unittest.TestCase):
    def term(self,key,value,unit='KG',currency='USD'):
        return {'key':key,'value':value,'unit':unit,'currency':currency,'status':'suggested'}
    def test_price_numeric_not_textual_collision(self):
        _,warnings=normalize_term_keys({'terms':[self.term('unit price','5'),self.term('단가','5.00')]})
        self.assertEqual(warnings,[])
    def test_real_price_conflict_stays_visible(self):
        _,warnings=normalize_term_keys({'terms':[self.term('unit price','4'),self.term('단가','5')]})
        self.assertTrue(any(i['key']=='unit_price' for i in warnings))
    def test_price_per_ton_and_per_kg_equivalent(self):
        _,warnings=normalize_term_keys({'terms':[self.term('price per kg','5','KG'),self.term('price per mt','5000','MT')]})
        self.assertEqual(warnings,[])
    def test_quantity_mt_and_kg_equivalent(self):
        _,warnings=normalize_term_keys({'terms':[self.term('qty','50','MT',''),self.term('quantity','50000','KG','')]})
        self.assertEqual(warnings,[])
    def test_dollar_not_assumed_usd(self):
        _,warnings=normalize_term_keys({'terms':[self.term('unit_price','$5','KG',''),self.term('unit_price','5','KG','USD')]})
        self.assertTrue(warnings)
    def test_delivery_schedule_not_conflict(self):
        terms=[self.term('delivery','EXW 부산 창고','',''),self.term('인도조건','각 인수 일정과 수량을 확인하고 지연시 통지하여 협의한다','','')]
        out,warnings=normalize_term_keys({'terms':terms})
        self.assertEqual(warnings,[])
        self.assertEqual({i['key'] for i in out['terms']},{'delivery','delivery_schedule_notes'})
    def test_different_incoterms_still_conflict(self):
        _,warnings=normalize_term_keys({'terms':[self.term('delivery','EXW 부산','',''),self.term('delivery','CIF Mumbai','','')]})
        self.assertTrue(warnings)
    def test_final_rejects_placeholders(self):
        snap={'contract_type':'sale','terms':[],'parties':[],'issues':[],
              'clauses':[{'sentences':[{'id':'s1','text':'종료일은 [서명 전 확인]으로 한다.'}]}]}
        issues=validate_snapshot(snap,for_export=True,env={})
        self.assertTrue(any(i['code']=='unresolved_clause_placeholder' for i in issues))
        draft_issues=validate_snapshot(snap,for_export=False,env={})
        self.assertFalse(any(i['code']=='unresolved_clause_placeholder' for i in draft_issues))

if __name__=='__main__': unittest.main()
