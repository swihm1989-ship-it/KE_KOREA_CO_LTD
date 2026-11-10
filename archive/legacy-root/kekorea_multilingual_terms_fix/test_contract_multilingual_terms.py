import unittest
from copy import deepcopy
from Quotation_KEKOREA.contracts.clause_terms import merge_clause_candidates
from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys

class MultilingualTermTests(unittest.TestCase):
    def test_three_languages_map_to_one_canonical_field(self):
        for key in ('단가', 'unit price', 'harga satuan', 'UNIT_PRICE'):
            with self.subTest(key=key):
                data, conflicts = normalize_term_keys({'terms': [{'key':key,'value':'5','currency':'USD'}]})
                self.assertEqual(data['terms'][0]['key'],'unit_price')
                self.assertEqual(data['terms'][0]['status'],'suggested')
                self.assertEqual(conflicts, [])

    def test_known_terms_and_unknown_are_preserved(self):
        data,_=normalize_term_keys({'terms':[{'key':'jumlah bulanan','value':'50000','unit':'KG/month'},
                                             {'key':'인도조건','value':'EXW Busan'},
                                             {'key':'very specific unusual clause','value':'ABC'}]})
        self.assertEqual([t['key'] for t in data['terms']], ['quantity','delivery','very specific unusual clause'])

    def test_approved_value_never_overwritten(self):
        snap={'terms':[{'key':'unit_price','value':'4','status':'confirmed','currency':'USD'}], 'parties': []}
        before=deepcopy(snap)
        out=merge_clause_candidates(snap, {'terms':[{'key':'harga satuan','value':'5','unit':'KG','currency':'USD'}], 'parties':[]})
        self.assertEqual(out['terms'][0]['value'],'4')
        self.assertEqual(out['terms'][0]['status'],'confirmed')
        self.assertEqual(snap,before)

    def test_conflict_kept_for_review_without_auto_resolve(self):
        snap={'terms':[], 'parties': []}
        out=merge_clause_candidates(snap, {'terms':[{'key':'단가','value':'4'}, {'key':'unit price','value':'5'}], 'parties':[]})
        self.assertEqual(out['terms'][0]['key'],'unit_price')
        self.assertEqual(out['terms'][0]['value'],'4')
        self.assertEqual(out['terms'][0]['status'],'suggested')
        self.assertEqual(len(out['clause_extraction_conflicts']),1)

if __name__=='__main__': unittest.main()
