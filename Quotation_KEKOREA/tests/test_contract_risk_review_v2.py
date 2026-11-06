"""Non-network tests for additive risk review. Existing review, editing and policy are immutable."""
from unittest.mock import patch
import unittest

from Quotation_KEKOREA.contracts.risk_review_workspace import (
    page_items, replace_variables, review_full_contract, suggest_alternatives,
    preview_proposal, PROTECTED_SENTENCES,
)
from Quotation_KEKOREA.contracts.models import new_snapshot


def sample():
    s = new_snapshot('risk-test', 'sale', 'ko')
    s['revision'] = 3
    s['clauses'] = [{'id':'a','title':'Terms','order':1,'sentences':[
        {'id':f's{i}', 'text':f'Clause {i}', 'term_ids':[], 'source_refs':[]} for i in range(1,28)]}]
    return s


class ExpandedReviewTests(unittest.TestCase):
    def test_pagination_of_twelve_findings(self):
        items=[{'title':str(i)} for i in range(12)]
        self.assertEqual([len(page_items(items,i)['items']) for i in (1,2,3)], [5,5,2])
        self.assertEqual(page_items(items,3)['pages'],3)

    def test_every_clause_chunk_is_reviewed_and_sorted(self):
        s=sample()
        calls=[]
        def fake(subset,sources,*,env):
            ids=[x['id'] for c in subset['clauses'] for x in c['sentences']]
            calls.append(ids)
            return [{'sentence_id':i,'severity':'high','title':i,'reason':'Reason','suggestion':'Edit','source_ids':[]} for i in ids[:5]]
        out=review_full_contract(s,[],env={},reviewer=fake)
        self.assertEqual(len(calls),3)
        self.assertEqual(sorted({i for part in calls for i in part}),sorted(f's{i}' for i in range(1,28)))
        self.assertEqual(len(out),15)

    def test_variable_substitution_is_safe_and_marks_missing(self):
        self.assertEqual(replace_variables('Pay {rate}% to {party}.', {'rate':'20','party':''}),
                         'Pay 20% to [확인 필요: party].')
        self.assertIn('__import__',replace_variables('{__import__}',{}))

    def test_three_recommendations_are_structurally_checked(self):
        s=sample()
        finder={'sentence_id':'s1','title':'Risk','reason':'Reason'}
        good={'options':[{'label':v,'template':'Pay {rate}%.'} for v in ('균형형','보호형','협의형')],
              'variables':[{'key':'rate','label':'위약금률','value':'20'}]}
        with patch('Quotation_KEKOREA.contracts.service._call',return_value=good) as ai:
            ret=suggest_alternatives(s,finder,env={})
        self.assertEqual(ai.call_count,1)
        self.assertEqual(len(ret['options']),3)
        with patch('Quotation_KEKOREA.contracts.service._call',return_value={**good,'variables':[]}):
            with self.assertRaises(ValueError):
                suggest_alternatives(s,finder,env={})

    def test_preview_does_not_modify_original_or_revision(self):
        s=sample()
        proposal=preview_proposal(s,{'s1':'Suggested'})
        self.assertEqual(s['clauses'][0]['sentences'][0]['text'],'Clause 1')
        self.assertEqual(s['revision'],3)
        self.assertEqual(proposal['changes'][0]['proposed_text'],'Suggested')
        with self.assertRaises(ValueError):
            preview_proposal(s,{'commission_payment_sentence_0':'changed'})


if __name__=='__main__':unittest.main()

try:
    import importlib.util as _importlib_util
    _streamlit_ready = _importlib_util.find_spec('streamlit') is not None
except (ImportError, ValueError):
    _streamlit_ready = False


@unittest.skipUnless(_streamlit_ready, 'Streamlit is not installed')
class RiskReviewStreamlitTests(unittest.TestCase):
    """End-to-end UI check using the existing in-memory contract repository fixture."""
    def setUp(self):
        from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests
        ThreeBoxUiTests.setUp(self)

    def run_app(self):
        from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests
        ThreeBoxUiTests.run_app(self)

    def test_paginate_select_apply_updates_preview_not_persisted_contract(self):
        findings = [{'title':f'Risk {i}', 'severity':'medium', 'reason':'Check',
                     'suggestion':'Consider alternative', 'sentence_id':'s1' if i%2 else 's2',
                     'source_ids':[]} for i in range(12)]
        self.at.session_state['contract_rag_risk_sample'] = {
            'revision':1, 'findings': findings, 'sources':[], 'notices':[]}
        self.at.session_state['risk_alternatives_sample_1_s1'] = {
            'options': [{'label':'균형형','template':'{rate}% agreed commission'},
                        {'label':'권리 보호형','template':'{rate}% of receipts'},
                        {'label':'보수적 협의형','template':'{rate}% [to be confirmed]'}],
            'variables':[{'key':'rate','label':'커미션 (%)','value':'20'}]}
        self.at.session_state['risk_alternatives_sample_1_s2'] = {
            'options': [{'label':'균형형','template':'New agreement'},
                        {'label':'권리 보호형','template':'Alternative clause'},
                        {'label':'보수적 협의형','template':'TBD clause'}], 'variables':[]}
        self.run_app()
        self.assertEqual(self.at.session_state['risk_page_sample_1'],1)
        self.at.button(key='risk_nav_sample_2').click()
        self.run_app()
        self.assertEqual(self.at.session_state['risk_page_sample_1'],2)
        # Page 2 includes risk #6 (index 5), which targets s1.
        # Risk #7 (index 6) targets s2, so selecting #7 cannot render the s1 editor.
        self.at.button(key='risk_pick_sample_1_6').click()
        self.run_app()
        self.at.text_area(key='risk_edited_sample_1_s1').set_value('User corrected 14% commission')
        self.at.button(key='risk_apply_preview_sample_1_s1').click()
        self.run_app()
        self.assertEqual(self.at.session_state['contract_risk_preview_sample']['sentences']['s1'],
                         'User corrected 14% commission')
        self.assertEqual(self.repo.records['sample']['current_revision'],1)
        # The same sentence button now previews edited text in the document box.
        self.assertEqual(self.at.button(key='contract_sentence_sample_s1').label,
                         'User corrected 14% commission')
