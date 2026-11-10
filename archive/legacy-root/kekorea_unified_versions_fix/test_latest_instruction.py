import unittest
from Quotation_KEKOREA.contracts.latest_instruction import (
    candidate_from_latest, latest_unapplied_request, instruction_hash,
)

class LatestInstructionTests(unittest.TestCase):
    def test_recent_explicit_change_survives_reopen_as_review_request(self):
        snapshot={'contract_type':'sale','terms':[{'key':'delivery','value':'EXW Busan Warehouse','status':'confirmed'}], 'parties':[]}
        messages=[{'role':'user','content':'EXW Busan Warehouse'},
                  {'role':'user','content':'EXW KE KOREA 서울 창고로 수정.'}]
        self.assertEqual(latest_unapplied_request(messages,snapshot),messages[-1]['content'])

    def test_approved_chat_hash_does_not_reoffer_old_request(self):
        msg='EXW KE KOREA 서울 창고로 수정.'
        snapshot={'last_approved_chat_hash':instruction_hash(msg)}
        self.assertIsNone(latest_unapplied_request([{'role':'user','content':msg}],snapshot))

    def test_newest_delivery_replaces_only_staged_candidate(self):
        original={'contract_type':'sale','terms':[
            {'key':'delivery','value':'EXW Busan Warehouse','status':'confirmed'},
            {'key':'unit_price','value':'5','unit':'KG','currency':'USD','status':'confirmed'}],
            'parties':[]}
        analysis={'terms':[{'key':'delivery','value':'EXW KE KOREA 서울 창고','status':'suggested'},
                           {'key':'unit_price','value':'','status':'missing'}], 'parties':[]}
        candidate=candidate_from_latest(original, analysis)
        self.assertEqual(original['terms'][0]['value'],'EXW Busan Warehouse')
        self.assertEqual(candidate['terms'][0]['value'],'EXW KE KOREA 서울 창고')
        self.assertEqual(candidate['terms'][0]['status'],'suggested')
        self.assertEqual(candidate['terms'][1],original['terms'][1])

    def test_unchanged_confirmed_field_remains_confirmed(self):
        original={'contract_type':'sale','terms':[{'key':'unit_price','value':'5','status':'confirmed'}], 'parties':[]}
        candidate=candidate_from_latest(original, {'terms':[{'key':'unit price','value':'5'}], 'parties':[]})
        self.assertEqual(candidate['terms'][0]['status'],'confirmed')

if __name__ == '__main__': unittest.main()
