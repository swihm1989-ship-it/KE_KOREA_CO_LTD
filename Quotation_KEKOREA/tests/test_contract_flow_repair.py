import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.ui import _term_rows
from Quotation_KEKOREA.contracts.final_policy import final_document_blockers


class ContractFlowRepairTests(unittest.TestCase):
    def test_roles_are_not_duplicate_term_rows(self):
        snap={'contract_type':'sale','terms':[], 'parties':[
            {'roles':['seller'],'legal_name':'KE KOREA CO. LTD'},
            {'roles':['buyer'],'legal_name':'OCI Co. Ltd.'}]}
        keys={r['key'] for r in _term_rows(snap)}
        self.assertNotIn('buyer',keys)
        self.assertNotIn('seller',keys)

    def test_user_input_unit_does_not_require_second_ai_call(self):
        snap={'contract_type':'sale','terms':[{'key':'quantity','value':'50000','unit':'KG/월','status':'confirmed'}]}
        rows={r['key']:r for r in _term_rows(snap)}
        self.assertEqual(rows['unit']['value'],'KG')
        self.assertEqual(rows['unit']['status'],'AI 제안')

    def test_existing_explicit_unit_not_overwritten(self):
        snap={'contract_type':'sale','terms':[{'key':'unit','value':'MT','status':'confirmed'},
            {'key':'quantity','value':'50','unit':'KG','status':'suggested'}]}
        rows={r['key']:r for r in _term_rows(snap)}
        self.assertEqual(rows['unit']['value'],'MT')
        self.assertEqual(rows['unit']['status'],'확정')

    def test_sale_payment_label_is_not_commission(self):
        rows={r['key']:r for r in _term_rows({'contract_type':'sale','terms':[]})}
        self.assertEqual(rows['payment_trigger']['항목'],'매매대금 지급 조건')

    def test_unverified_symbol_is_never_silently_usd(self):
        rows={r['key']:r for r in _term_rows({'contract_type':'sale','terms':[
            {'key':'currency','value':'$','status':'suggested'}]})}
        self.assertEqual(rows['currency']['value'],'$')
        self.assertEqual(rows['currency']['status'],'AI 제안')

    def test_unresolved_prose_placeholder_blocks_final(self):
        snap={'contract_type':'sale','clauses':[{'sentences':[{'text':'[서명 전 확인]'}]}],
             'parties':[{'legal_name':'KE KOREA CO. LTD','roles':['seller']},
                        {'legal_name':'OCI Co. Ltd.','roles':['buyer']}], 'pending_reconciliation':False}
        self.assertTrue(final_document_blockers(snap))
