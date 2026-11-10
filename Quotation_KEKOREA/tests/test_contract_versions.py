import unittest
from Quotation_KEKOREA.contracts.contract_versions import copy_contract, translate_contract, localized_term_label

class ContractVersionTests(unittest.TestCase):
    def fixture(self):
        return {'contract_id':'abc','revision':5,'title':'공급 계약','contract_type':'sale','language':'ko',
                'clauses':[{'id':'c1','title':'인도 조건','order':1,'sentences':[
                    {'id':'s1','text':'단가 USD 5/KG, EXW 서울 창고, 50MT/월로 한다.', 'term_ids':['unit_price'],'source_refs':[]}]}],
                'terms':[{'id':'t1','key':'unit_price','value':'5','unit':'KG','currency':'USD','status':'confirmed'},
                         {'id':'t2','key':'delivery','value':'EXW 서울 창고','status':'confirmed'}],
                'parties':[{'id':'p1','roles':['seller'],'legal_name':'KE KOREA CO. LTD','status':'confirmed'}],
                'issues':[],'reference_ids':['source1']}
    def test_copy_keeps_latest_terms_and_clauses_without_overwriting_original(self):
        original=self.fixture()
        result=copy_contract(original)
        self.assertEqual(result['terms'][1]['value'],'EXW 서울 창고')
        self.assertEqual(result['clauses'][0]['sentences'][0]['text'],original['clauses'][0]['sentences'][0]['text'])
        self.assertEqual(result['parties'][0]['legal_name'],'KE KOREA CO. LTD')
        self.assertNotEqual(result['clauses'][0]['sentences'][0]['id'],'s1')
        self.assertEqual(result['reference_ids'],[])
        self.assertEqual(original['revision'],5)
    def test_translation_keeps_original_numbers_codes_and_creates_immediate_clauses(self):
        def fake_call(instructions,payload,*,env):
            translations={
                '공급 계약':'Supply Agreement','인도 조건':'Delivery Terms',
                '단가 USD 5/KG, EXW 서울 창고, 50MT/월로 한다.':'Price USD 5/KG, EXW Seoul warehouse, 50MT/month.',
                'EXW 서울 창고':'EXW Seoul warehouse'}
            return {'translations':[{'key':s['key'],'text':translations.get(s['text'],s['text'])}
                                    for s in payload['segments']]}
        result=translate_contract(self.fixture(),'en',env={},caller=fake_call)
        self.assertEqual(result['language'],'en')
        self.assertEqual(result['clauses'][0]['sentences'][0]['text'],'Price USD 5/KG, EXW Seoul warehouse, 50MT/month.')
        self.assertEqual(result['terms'][0]['value'],'5')
        self.assertEqual(result['parties'][0]['legal_name'],'KE KOREA CO. LTD')
    def test_protected_code_mismatch_retries_only_one_segment(self):
        original = self.fixture()
        calls = []
        def translate(_instructions, payload, *, env):
            calls.append([item['key'] for item in payload['segments']])
            rows = []
            for item in payload['segments']:
                value = item['text']
                if '단가 USD 5/KG' in value:
                    value = ('The price is USD 5 per kilogram, EXW Seoul warehouse, '
                             '50MT/month.')
                elif '인도 조건' == value:
                    value = 'Delivery Conditions'
                elif value == '공급 계약':
                    value = 'Supply Agreement'
                elif value == 'EXW 서울 창고':
                    value = 'EXW Seoul warehouse'
                if 'previous_translation' in payload:
                    value = 'The price is USD 5/KG, EXW Seoul warehouse, 50MT/month.'
                rows.append({'key': item['key'], 'text': value})
            return {'translations': rows}
        output = translate_contract(original, 'en', env={}, caller=translate)
        self.assertEqual(output['clauses'][0]['sentences'][0]['text'],
                         'The price is USD 5/KG, EXW Seoul warehouse, 50MT/month.')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1], ['clause:0:sentence:0'])
        self.assertEqual(original['language'], 'ko')

    def test_changed_protected_code_still_blocks_after_retry(self):
        original = self.fixture()
        def translate(_instructions, payload, *, env):
            return {'translations': [
                {'key': item['key'], 'text': item['text'].replace('EXW', 'FOB')}
                for item in payload['segments']
            ]}
        with self.assertRaisesRegex(ValueError, '통화/단위/Incoterms 변경이 재번역'):
            translate_contract(original, 'en', env={}, caller=translate)
        self.assertEqual(original['language'], 'ko')

    def test_unrelated_numeric_change_does_not_retry(self):
        original = self.fixture()
        calls = []
        def translate(_instructions, payload, *, env):
            calls.append(payload)
            return {'translations': [
                {'key': item['key'], 'text': item['text'].replace('50MT', '60MT')}
                for item in payload['segments']
            ]}
        with self.assertRaisesRegex(ValueError, '번역 숫자/금액 불일치'):
            translate_contract(original, 'en', env={}, caller=translate)
        self.assertEqual(len(calls), 1)

    def test_english_condition_label_is_localized_without_changing_key(self):
        self.assertEqual(localized_term_label('payment_trigger','en','매매대금 지급 조건'),'Payment terms')
        self.assertEqual(localized_term_label('payment_trigger','ko','매매대금 지급 조건'),'매매대금 지급 조건')

    def test_reject_translation_altering_price(self):
        def bad(instructions,payload,*,env):
            return {'translations':[{'key':x['key'],'text':x['text'].replace('USD 5/KG','USD 4/KG')}
                                    for x in payload['segments']]}
        with self.assertRaisesRegex(ValueError,'숫자'):
            translate_contract(self.fixture(),'en',env={},caller=bad)

if __name__=='__main__': unittest.main()
