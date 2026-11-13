import copy
import io
import json
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.orchestration.tests.mail_fixtures import cases


def response(data):
    return io.BytesIO(json.dumps({'status':'completed','usage':{'input_tokens':100,'output_tokens':10},
        'output':[{'content':[{'type':'output_text','text':json.dumps(data)}]}]}).encode())


class MailIntakePolicyTests(unittest.TestCase):
    def test_plain_pi_request_and_cipl_aliases(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import prepare_mail_request
        for text,expected in [('Please provide PI for below:',('PI',)),('Please provide CIPL',('CI','PL')),
                              ('견적서를 부탁합니다',('PI',)),('Prepare CI using the attached PI',('CI',))]:
            self.assertEqual(prepare_mail_request('Hello',text).kinds,expected)

    def test_latest_request_excludes_history_and_explicit_negation(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import prepare_mail_request
        request=prepare_mail_request('Re: PI','Please prepare PO. No need for PI.\nOn Monday Buyer wrote:\n> Please send PI and contract')
        self.assertEqual(request.kinds,('PO',))
        self.assertIn('Buyer wrote',request.instruction) # retain source facts for AI, not routing

    def test_long_mail_is_rejected_instead_of_silently_truncated(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import prepare_mail_request
        with self.assertRaises(ValueError):
            prepare_mail_request('PI','x'*13000)

    def test_no_consent_makes_no_provider_request(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import extract_mail_candidates
        with patch('Quotation_KEKOREA.agent.extractor.extract_trade_data') as provider:
            with self.assertRaises(PermissionError):
                extract_mail_candidates('PI',('PI',),{},consent=False)
            provider.assert_not_called()

    def test_provider_cannot_approve_or_claim_a_source_pi(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import extract_mail_candidates
        case=cases()[8]
        raw=copy.deepcopy(case['trade']);raw['_ci_from_pi']=True;raw['ready_for_issue']=True
        raw['items'][0]['price_override_confirmed']=True
        result=extract_mail_candidates(case['body'],('CI','PL'),{'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},
             consent=True,trade_opener=lambda *a,**kw:response(raw))
        self.assertNotIn('_ci_from_pi',result['candidates']['CI'])
        self.assertNotIn('price_override_confirmed',result['candidates']['CI']['items'][0])
        from Quotation_KEKOREA.agent.ci_import import ci_import_issues
        self.assertTrue(ci_import_issues(result['candidates']['CI']))

    def test_one_shot_token_stale_edits_and_clear_previous_files(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import queue_handoff, consume_pending
        from Quotation_KEKOREA.orchestration.adapters.whois_mail import parse_message
        case=cases()[0];mail=parse_message(case['id'],case['raw'])
        state={'master_legacy_files':'old','ai_intake_candidates':'old','ai_intake_contract_consent':True}
        queue_handoff(state,mail,extract=True)
        text=state['ai_intake_instruction']
        self.assertNotIn('master_legacy_files',state)
        self.assertNotIn('ai_intake_contract_consent',state)
        self.assertTrue(consume_pending(state,text))
        self.assertFalse(consume_pending(state,text))
        queue_handoff(state,mail,extract=True)
        self.assertFalse(consume_pending(state,text+'CHANGED'))

    def test_fragment_handoff_defers_sidebar_navigation_until_full_app_rerun(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import (
            queue_handoff, consume_mail_navigation, consume_pending,
        )
        from Quotation_KEKOREA.orchestration.adapters.whois_mail import parse_message
        case = cases()[0]
        mail = parse_message(case['id'], case['raw'])
        state = {'master_page': '메일함', 'master_pdf_quantity': 'old',
                 'ai_intake_consent': False}
        queue_handoff(state, mail, extract=True, requested=['PI'], navigate=False)
        # The sidebar radio already exists during a fragment-only rerun.
        self.assertEqual(state['master_page'], '메일함')
        self.assertEqual(state['ai_intake_mail_source']['kinds'], ['PI'])
        self.assertTrue(state['ai_intake_consent'])
        self.assertNotIn('master_pdf_quantity', state)
        state['master_mail_navigation_pending'] = True
        self.assertTrue(consume_mail_navigation(state))
        self.assertEqual(state['master_page'], 'AI 업무 요청')
        self.assertFalse(consume_mail_navigation(state))
        self.assertTrue(consume_pending(state, state['ai_intake_instruction']))
        self.assertFalse(consume_pending(state, state['ai_intake_instruction']))

    def test_draft_handoff_defers_navigation_without_external_ai_consent(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import (
            queue_handoff, consume_mail_navigation,
        )
        from Quotation_KEKOREA.orchestration.adapters.whois_mail import MailMessage
        mail = MailMessage('synthetic-mou-uid', subject='BIPV MoU 작성',
                           body='BIPV 설치 관련 MoU 작성 수정안 부탁드립니다')
        state = {'master_page': '메일함'}
        queue_handoff(state, mail, extract=False, navigate=False)
        self.assertEqual(state['master_page'], '메일함')
        self.assertEqual(state['ai_intake_mail_source']['kinds'], ['CONTRACT'])
        self.assertFalse(state['ai_intake_consent'])
        self.assertNotIn('ai_intake_mail_pending', state)
        state['master_mail_navigation_pending'] = True
        self.assertTrue(consume_mail_navigation(state))
        self.assertEqual(state['master_page'], 'AI 업무 요청')

    def test_ci_without_original_pi_remains_blocked_by_existing_validator(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import extract_mail_candidates
        from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
        case=cases()[6]
        result=extract_mail_candidates(case['body'],('CI',),{'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},
            consent=True,trade_opener=lambda *a,**k:response(case['trade']))
        blockers=validate_and_calculate(result['candidates']['CI'])['blocking_issues']
        self.assertTrue(any('attached PI' in reason for reason in blockers))

    def test_selected_original_pi_enables_only_ci_import_and_preserves_shipping_rows(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import extract_mail_candidates
        import pymupdf
        doc=pymupdf.open();page=doc.new_page();page.insert_text((50,50),'PROFORMA INVOICE - SYNTHETIC TEST ONLY')
        attachment={'name':'synthetic-pi.pdf','mime_type':'application/pdf','data':doc.tobytes()};doc.close()
        case=cases()[8];trade=copy.deepcopy(case['trade']);trade['source_document_type']='PI'
        before=copy.deepcopy(trade)
        result=extract_mail_candidates(case['body'],('CI','PL'),{'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},
            consent=True,attachments=[attachment],trade_opener=lambda *a,**k:response(trade))
        self.assertTrue(result['candidates']['CI']['_ci_from_pi'])
        self.assertNotIn('_ci_from_pi',result['candidates']['PL'])
        self.assertEqual(trade,before)
        self.assertEqual(result['candidates']['PL']['items'][0]['gross_weight_kg'],trade['items'][0]['gross_weight_kg'])

    def test_buyer_address_is_never_inferred_as_ship_to(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import extract_mail_candidates
        case=cases()[1];trade=copy.deepcopy(case['trade']);trade['ship_to']=trade['buyer']['address']
        result=extract_mail_candidates(case['body'],('PI',),{'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},
            consent=True,trade_opener=lambda *a,**k:response(trade))
        self.assertFalse(result['candidates']['PI'].get('ship_to'))

    def test_human_filled_missing_notice_is_resolved_but_conflicts_and_source_pi_are_not(self):
        from Quotation_KEKOREA.orchestration.workflows.intake_followups import apply_answer
        data={'PI':{'buyer':{},'items':[{'quantity':'0'}],
                    'missing_fields':['buyer.address','Unclear item 2 price'],
                    'conflicts':['Different shipping addresses']}}
        updated=apply_answer(data,'buyer.address','Fixed new address')
        self.assertEqual(updated['PI']['missing_fields'],['Unclear item 2 price'])
        self.assertEqual(updated['PI']['conflicts'],data['PI']['conflicts'])

    def test_missing_contract_terms_still_expose_recoverable_trade_and_contract_candidates(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import extract_mail_candidates
        case=cases()[12];analysis=copy.deepcopy(case['analysis'])
        analysis['terms'].append({'key':'governing_law','value':None,'status':'missing','source_refs':[]})
        result=extract_mail_candidates(case['body'],('PI','CONTRACT'),{'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},
            consent=True,trade_opener=lambda *a,**k:response(case['trade']),contract_opener=lambda *a,**k:response(analysis))
        self.assertIn('PI',result['candidates'])
        self.assertIn('CONTRACT',result['candidates'])
        self.assertFalse(any(t['key']=='governing_law' for t in result['candidates']['CONTRACT']['terms']))

    def test_quantity_edits_recalculate_paid_and_shipping_including_promotions(self):
        from Quotation_KEKOREA.orchestration.workflows.intake_followups import apply_answer
        from Quotation_KEKOREA.orchestration.workflows.mail_trade_normalization import synchronize_nullable_quantities
        from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
        case=cases()[1];data=copy.deepcopy(case['trade'])
        data['items'][0].update(paid_quantity='2000',free_quantity='0',shipped_quantity='2000',discount_percent='0')
        updated=apply_answer({'PI':data},'item.quantity','3000')['PI']
        checked=validate_and_calculate(updated)
        self.assertEqual(checked['items'][0]['quantity'],'3000')
        self.assertEqual(checked['total'],'675.00')
        promo=copy.deepcopy(data);promo['items'][0].update(quantity='3',paid_quantity=None,free_quantity=None,shipped_quantity=None,promotion='3+1')
        synchronized=synchronize_nullable_quantities(promo)
        self.assertEqual(synchronized['items'][0]['free_quantity'],'1')
        revised=apply_answer({'PI':synchronized},'item.quantity','6')['PI']['items'][0]
        self.assertEqual(revised['free_quantity'],'2')
        self.assertEqual(revised['shipped_quantity'],'8')


class DummyMailTests(unittest.TestCase):
    pass


def make_case(case):
    def test(self):
        from Quotation_KEKOREA.orchestration.workflows.mail_intake import prepare_mail_request, extract_mail_candidates
        from Quotation_KEKOREA.orchestration.adapters.whois_mail import parse_message
        from Quotation_KEKOREA.agent.trade_documents import validate_and_calculate
        from decimal import Decimal
        mail=parse_message(case['id'],case['raw'])
        request=prepare_mail_request(mail.subject,mail.body)
        self.assertEqual(request.kinds,case['kinds'])
        provider_calls=[]
        def provider(req,**kwargs):
            payload=json.loads(req.data)
            provider_calls.append(payload)
            self.assertNotIn('PRIVATE SAVED CONTRACT',str(payload))
            return response(copy.deepcopy(case['trade']))
        def contract_provider(*a,**k):
            return response(copy.deepcopy(case['analysis']))
        result=extract_mail_candidates(request.instruction,request.kinds,
              {'OPENAI_API_KEY':'SYNTHETIC','OPENAI_MODEL':'gpt-6-luna'},consent=True,
              trade_opener=provider,contract_opener=contract_provider)
        self.assertEqual(tuple(result['candidates']),case['kinds'])
        for kind,doc in result['candidates'].items():
            if kind=='CONTRACT':
                self.assertEqual(doc['clauses'],[])
                self.assertTrue(all(t['status']=='suggested' for t in doc['terms']))
                continue
            self.assertEqual(len(doc['items']),len(case['trade']['items']))
            self.assertEqual(doc['currency'],case['trade']['currency'])
            self.assertEqual(doc['buyer']['legal_name'],case['trade']['buyer']['legal_name'])
            self.assertEqual(doc['items'][0]['quantity'],case['trade']['items'][0]['quantity'])
            self.assertEqual(doc['items'][0]['price_basis'],case['trade']['items'][0]['price_basis'])
            self.assertFalse(doc.get('ready_for_issue',False))
            if kind in ('PI','PO'):
                checked=validate_and_calculate(doc)
                self.assertEqual(Decimal(checked['total']),case['expected_total'])
                self.assertEqual(checked['blocking_issues'],[])
            if kind=='PL':
                self.assertEqual(doc['actual_package_count'],case['trade']['actual_package_count'])
                self.assertEqual(doc['items'][0]['net_weight_kg'],case['trade']['items'][0]['net_weight_kg'])
        self.assertEqual(len(provider_calls),int(any(k!='CONTRACT' for k in case['kinds'])))
    return test


for case in cases():
    setattr(DummyMailTests,'test_'+case['id'].replace('-','_'),make_case(case))
