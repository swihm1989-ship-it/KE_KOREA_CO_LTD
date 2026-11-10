import unittest
from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys
from Quotation_KEKOREA.contracts.clause_terms import merge_clause_candidates

class ExpandedAliasTests(unittest.TestCase):
    def mapped(self,key,value='5',unit=None,currency='USD'):
        rows,_=normalize_term_keys({'terms':[{'key':key,'value':value,'unit':unit,'currency':currency}]})
        return rows['terms'][0]['key']

    def test_price_aliases(self):
        for alias in ('단가','Unit Price','Price per KG','Price/MT','harga satuan','harga per kg','u/p','kg당 가격'):
            with self.subTest(alias=alias):
                self.assertEqual(self.mapped(alias),'unit_price')

    def test_generic_price_is_candidate_not_certified(self):
        result,warnings=normalize_term_keys({'terms':[{'key':'price','value':'5'}]})
        self.assertEqual(result['terms'][0]['key'],'unit_price')
        self.assertEqual(result['terms'][0]['status'],'suggested')
        self.assertTrue(warnings)

    def test_quantity_synonyms(self):
        for alias in ('Volume','vol','qty','quantity','monthly volume','tonnage','weight','jumlah','kuantitas','jumlah bulanan','월 물량','중량'):
            with self.subTest(alias=alias):
                self.assertEqual(self.mapped(alias),'quantity')

    def test_units_are_not_quantities(self):
        for alias in ('KG','MT','pcs','kilograms','metric tons'):
            with self.subTest(alias=alias):
                self.assertEqual(self.mapped(alias,value='KG'), 'unit')

    def test_total_value_vs_unit_price(self):
        self.assertEqual(self.mapped('contract value', '1000000'), 'total_contract_value')
        self.assertEqual(self.mapped('value', 'USD 5/KG'), 'unit_price')
        result,warnings=normalize_term_keys({'terms':[{'key':'value','value':'1000000'}]})
        self.assertEqual(result['terms'][0]['key'],'value')
        self.assertTrue(warnings)

    def test_misc_aliases(self):
        cases={'syarat pembayaran':'payment_trigger','payment due date':'payment_deadline',
               'incoterms':'delivery','penyelesaian sengketa':'dispute_resolution',
               'arbitrase':'dispute_resolution','검수':'inspection_claims',
               'masa kontrak':'contract_duration','jumlah total kontrak':'total_contract_quantity',
               'commission rate':'commission_formula','produk':'products','effective date':'contract_date'}
        for alias,expected in cases.items():
            with self.subTest(alias=alias): self.assertEqual(self.mapped(alias),expected)

    def test_duplicate_price_conflicts_and_approved_preserved(self):
        snap={'terms':[{'key':'unit_price','value':'4','status':'confirmed','currency':'USD'}], 'parties': []}
        out=merge_clause_candidates(snap,{'terms':[{'key':'price per kg','value':'5','currency':'USD'},
                                                  {'key':'harga satuan','value':'6','currency':'USD'}], 'parties': []})
        self.assertEqual(out['terms'][0]['value'],'4')
        self.assertEqual(out['terms'][0]['status'],'confirmed')
        self.assertTrue(out['clause_extraction_conflicts'])
