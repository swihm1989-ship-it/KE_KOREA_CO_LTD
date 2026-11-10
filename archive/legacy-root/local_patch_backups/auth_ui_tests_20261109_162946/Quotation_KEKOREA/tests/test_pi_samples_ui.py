"""PI sample edits must survive sidebar navigation and invalidate old files."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_order_promotions import order


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
class PiSamplesUiTests(unittest.TestCase):
    def test_prompt_manual_edits_totals_sidebar_and_stale_downloads(self):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / 'app.py'
        env = {'OPENAI_API_KEY': 'test', **{f'KEKOREA_USD_{k}': 'TEST' for k in
               ('BENEFICIARY', 'BANK_NAME', 'BRANCH', 'SWIFT', 'ACCOUNT_NUMBER', 'BANK_ADDRESS')}}
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value=env), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.counterparties.load_company_profiles', return_value=[]), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
            at = AppTest.from_file(str(path)).run(timeout=20)
            prompt = 'Create PI for Dearglow. 샘플도 있어. Currency: USD. 0% discount. Ship To: Test Warehouse.'
            at.text_area[0].set_value(prompt).run(timeout=20)
            doc = order()
            doc['ship_to'] = 'Test Warehouse'
            with patch('Quotation_KEKOREA.agent.extractor.extract_trade_data', return_value=copy.deepcopy(doc)):
                next(b for b in at.button if b.label == '정보 추출 및 초안 검토').click().run(timeout=20)
                work = at.session_state['_document_workspaces']
                job = work.jobs.get(('PI 만들기', 'extract'))
                if job:
                    job.future.result(timeout=3)
                    at.run(timeout=20)
            self.assertFalse(at.exception)
            inputs = lambda label: next(e for e in at.text_input if e.label == label)
            self.assertTrue(any(e.label == 'Sample 1: quantity' for e in at.text_input))
            self.assertTrue(next(b for b in at.button if b.label == 'Create PDF').disabled)
            for label, value in (('Sample 1: product name', 'Trial Toner'), ('Sample 1: quantity', '5'),
                                 ('Sample 1: unit price', '0')):
                inputs(label).set_value(value).run(timeout=20)
            result = lambda: json.loads(at.session_state['rendered_json'])['document']
            self.assertEqual(result()['total'], '20.00')
            self.assertEqual(result()['items'][-1]['display_quantity'], '5')
            self.assertFalse(next(b for b in at.button if b.label == 'Create PDF').disabled)
            self.assertEqual(result()['items'][-1]['product_name'], 'Trial Toner')
            inputs('Sample 1: product name').set_value('Cell Memory Cream').run(timeout=20)
            self.assertEqual(result()['items'][-1]['product_name'], 'Cell Memory Cream')
            at.session_state['rendered_paths'] = {'pdf': 'previous.pdf'}
            inputs('Sample 1: unit price').set_value('0.25').run(timeout=20)
            self.assertEqual(result()['total'], '21.25')
            self.assertEqual(at.session_state['rendered_paths'], {})
            at.sidebar.radio[0].set_value('PO 만들기').run(timeout=20)
            at.sidebar.radio[0].set_value('PI 만들기').run(timeout=20)
            self.assertEqual(inputs('Sample 1: unit price').value, '0.25')
            self.assertEqual(inputs('Sample 1: product name').value, 'Cell Memory Cream')
            self.assertEqual(result()['total'], '21.25')
            inputs('Sample 1: unit price').set_value('-1').run(timeout=20)
            self.assertTrue(next(b for b in at.button if b.label == 'Create PDF').disabled)
            inputs('Sample 1: unit price').set_value('0').run(timeout=20)
            next(b for b in at.button if b.label == '샘플 행 추가').click().run(timeout=20)
            self.assertTrue(any(e.label == 'Sample 2: quantity' for e in at.text_input))
            next(e for e in at.checkbox if e.label == 'Sample 2: include in invoice').uncheck().run(timeout=20)
            self.assertEqual(len(result()['items']), 2)
            self.assertFalse(next(b for b in at.button if b.label == 'Create PDF').disabled)

    def test_sample_only_pi_needs_no_ordinary_discount_and_new_extraction_resets_inputs(self):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / 'app.py'
        env = {'OPENAI_API_KEY': 'test', **{f'KEKOREA_USD_{k}': 'TEST' for k in
               ('BENEFICIARY', 'BANK_NAME', 'BRANCH', 'SWIFT', 'ACCOUNT_NUMBER', 'BANK_ADDRESS')}}
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value=env), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.counterparties.load_company_profiles', return_value=[]), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
            at = AppTest.from_file(str(path)).run(timeout=20)
            at.text_area[0].set_value('Create PI. SaMpLe도 있어. Currency: USD. Ship To: Test Warehouse.').run(timeout=20)
            doc = order()
            doc.update(items=[], ship_to='Test Warehouse')
            def extract():
                with patch('Quotation_KEKOREA.agent.extractor.extract_trade_data', return_value=copy.deepcopy(doc)):
                    next(b for b in at.button if b.label == '정보 추출 및 초안 검토').click().run(timeout=20)
                    job = at.session_state['_document_workspaces'].jobs.get(('PI 만들기', 'extract'))
                    if job:
                        job.future.result(timeout=3)
                        at.run(timeout=20)
            extract()
            for label, value in (('Sample 1: product name', 'Trial Toner'), ('Sample 1: quantity', '5'), ('Sample 1: unit price', '0')):
                next(e for e in at.text_input if e.label == label).set_value(value).run(timeout=20)
            self.assertFalse(at.exception)
            result = json.loads(at.session_state['rendered_json'])['document']
            self.assertEqual(result['total'], '0.00')
            self.assertFalse(any('discount' in issue.lower() for issue in result['blocking_issues']))
            self.assertFalse(next(b for b in at.button if b.label == 'Create PDF').disabled)
            extract()
            self.assertEqual(next(e for e in at.text_input if e.label == 'Sample 1: quantity').value, '')
            self.assertTrue(next(b for b in at.button if b.label == 'Create PDF').disabled)
