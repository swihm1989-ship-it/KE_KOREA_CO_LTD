"""Exercise event commands and late quantity completion through PO/PI screens."""
from Quotation_KEKOREA.tests.auth_test_helpers import isolated_authenticated_ui_tests
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_order_promotions import RULES, order


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
@isolated_authenticated_ui_tests
class OrderPromotionsUiTests(unittest.TestCase):
    def test_six_commands_reach_po_pi_review_and_enable_document_creation(self):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / 'app.py'
        env = {'OPENAI_API_KEY': 'test', **{f'KEKOREA_USD_{k}': 'TEST' for k in
               ('BENEFICIARY', 'BANK_NAME', 'BRANCH', 'SWIFT', 'ACCOUNT_NUMBER', 'BANK_ADDRESS')}}
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value=env), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
            for dtype in ('PI', 'PO'):
                for rule, (free, shipped) in RULES.items():
                    with self.subTest(dtype=dtype, rule=rule):
                        doc = order(dtype)
                        doc['ship_to'] = 'Test Warehouse'
                        at = AppTest.from_file(str(path))
                        at.session_state['selected_document_page'] = dtype + ' 만들기'
                        at.run(timeout=20)
                        at.text_area[0].set_value(f'Create {dtype}. Currency: USD. All products {rule} promotion. Ship To: Test Warehouse.').run(timeout=20)
                        with patch('Quotation_KEKOREA.agent.extractor.extract_trade_data', return_value=copy.deepcopy(doc)):
                            next(b for b in at.button if b.label == '정보 추출 및 초안 검토').click().run(timeout=20)
                            work = at.session_state['_document_workspaces']
                            job = work.jobs.get((dtype + ' 만들기', 'extract'))
                            if job:
                                job.future.result(timeout=3)
                                at.run(timeout=20)
                        self.assertFalse(at.exception)
                        result = json.loads(at.session_state['rendered_json'])['document']
                        self.assertEqual(result['items'][0].get('promotion'), rule)
                        self.assertEqual(result['items'][0]['free_quantity'], free)
                        self.assertEqual(result['items'][0]['shipped_quantity'], shipped)
                        self.assertEqual(result['total'], '20.00' if dtype == 'PI' else '20')
                        self.assertFalse(next(b for b in at.button if b.label == 'Create PDF').disabled)

    def test_late_quantity_input_updates_advanced_details_and_event_quantities(self):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / 'app.py'
        doc = order('PO')
        doc['items'][0].update(promotion='4+3', quantity=None, paid_quantity=None, shipped_quantity=None)
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
            at = AppTest.from_file(str(path))
            at.session_state['selected_document_page'] = 'PO 만들기'
            at.session_state['trade_draft_page'] = 'PO 만들기'
            at.session_state['trade_draft'] = doc
            at.run(timeout=20)
            next(e for e in at.text_input if e.label == 'Item 1: quantity *').set_value('10').run(timeout=20)
            self.assertFalse(at.exception)
            details = json.loads(next(e for e in at.text_area if e.label == 'Extracted details').value)
            self.assertEqual(details['items'][0]['free_quantity'], '6')
            self.assertEqual(details['items'][0]['shipped_quantity'], '16')

    def test_ambiguous_or_invalid_event_cannot_create_po(self):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / 'app.py'
        for promotion in ('unknown event', '0+1'):
            with self.subTest(promotion=promotion), \
                 patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
                 patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
                 patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
                doc = order('PO')
                doc['items'][0]['promotion'] = promotion
                at = AppTest.from_file(str(path))
                at.session_state['selected_document_page'] = 'PO 만들기'
                at.session_state['trade_draft_page'] = 'PO 만들기'
                at.session_state['trade_draft'] = doc
                at.run(timeout=20)
                self.assertFalse(at.exception)
                self.assertTrue(next(b for b in at.button if b.label == 'Create PDF').disabled)
