from Quotation_KEKOREA.tests.auth_test_helpers import isolated_authenticated_ui_tests
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_counterparties import PROFILE
from Quotation_KEKOREA.tests.test_review_fields import complete_draft


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
@isolated_authenticated_ui_tests
class CounterpartyUiTests(unittest.TestCase):
    def test_database_defaults_reach_pi_po_and_ci_without_overwriting_ship_to(self):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / 'app.py'
        env = dict(OPENAI_API_KEY='test', SUPABASE_URL='https://company-test.supabase.co', SUPABASE_SECRET_KEY='test')
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value=env), \
             patch('Quotation_KEKOREA.agent.pricing.load_supabase_catalog', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.counterparties.load_company_profiles', return_value=[PROFILE]), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(path, None, None)):
            for page, dtype, role in [('PI 만들기', 'PI', 'buyer'), ('PO 만들기', 'PO', 'seller'),
                                      ('CI 만들기', 'CI', 'buyer')]:
                with self.subTest(page=page):
                    doc = complete_draft()
                    doc.update(document_type=dtype, product_family='other', ship_to=None)
                    doc[role] = {'legal_name': 'Dearglow'}
                    at = AppTest.from_file(str(path))
                    at.session_state['selected_document_page'] = page
                    at.session_state['trade_draft_page'] = page
                    at.session_state['trade_draft'] = doc
                    at.run(timeout=20)
                    self.assertFalse(at.exception)
                    result = json.loads(at.session_state['rendered_json'])['document']
                    self.assertEqual(result[role]['legal_name'], PROFILE['legal_name'])
                    self.assertEqual(result[role]['address'], PROFILE['address'])
                    self.assertEqual(result[role]['contact'], PROFILE['contact'])
                    self.assertIsNone(result[role].get('phone'))
                    if dtype == 'PO':
                        self.assertIn(result.get('ship_to'), (None, 'N/A'))
                    else:
                        self.assertEqual(result['ship_to'], 'Test Delivery Address / Tel: N/A')
