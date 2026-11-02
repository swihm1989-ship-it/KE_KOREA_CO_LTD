"""Exercise document completion, reruns, and stale-download prevention in Streamlit."""
import importlib.util
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_review_fields import complete_draft


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
class ReviewUiTests(unittest.TestCase):
    def test_missing_inputs_update_document_and_invalidate_old_downloads(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        doc = complete_draft()
        doc.update(product_family='other', incoterms=None, payment_terms=None)
        doc['buyer']['email'] = None
        env = {'OPENAI_API_KEY': 'test', **{f'KEKOREA_USD_{key}': 'TEST' for key in
               ('BENEFICIARY', 'BANK_NAME', 'BRANCH', 'SWIFT', 'ACCOUNT_NUMBER', 'BANK_ADDRESS')}}
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value=env), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value={'products': []}), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(app_path, None, None)):
            at = AppTest.from_file(str(app_path))
            at.session_state['trade_draft'] = doc
            at.session_state['trade_draft_page'] = 'PI 만들기'
            at.run(timeout=20)
            self.assertFalse(at.exception)
            pdf_button = lambda: next(button for button in at.button if button.label == 'Create PDF')
            self.assertTrue(pdf_button().disabled)
            inputs = {entry.label: entry for entry in at.text_input}
            inputs['Delivery terms / Incoterms and named place *'].set_value('FOB Busan')
            inputs['Payment terms *'].set_value('100% before shipment')
            inputs['Buyer / customer: email'].set_value('N/A')
            at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertFalse(pdf_button().disabled)
            advanced = next(area for area in at.text_area if area.label == 'Extracted details')
            self.assertIn('FOB Busan', advanced.value)
            self.assertIn('100% before shipment', advanced.value)
            options = at.radio[0].options
            at.radio[0].set_value(options[1]).run(timeout=20)
            at.radio[0].set_value(options[0]).run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(next(entry for entry in at.text_input if entry.label.startswith('Delivery terms')).value,
                             'FOB Busan')
            self.assertFalse(pdf_button().disabled)
            at.session_state['rendered_paths'] = {'pdf': 'previous.pdf'}
            at.session_state['download_format'] = 'pdf'
            at.run(timeout=20)
            self.assertEqual(at.session_state['rendered_paths'], {'pdf': 'previous.pdf'})
            delivery = next(entry for entry in at.text_input if entry.label.startswith('Delivery terms'))
            delivery.set_value('CIF Singapore').run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['rendered_paths'], {})
            self.assertIn('CIF Singapore', next(area for area in at.text_area if area.label == 'Extracted details').value)
            delivery = next(entry for entry in at.text_input if entry.label.startswith('Delivery terms'))
            delivery.set_value('TO BE CONFIRMED').run(timeout=20)
            self.assertTrue(pdf_button().disabled)
            delivery = next(entry for entry in at.text_input if entry.label.startswith('Delivery terms'))
            delivery.set_value('CIF Singapore').run(timeout=20)
            self.assertFalse(pdf_button().disabled)
            new_doc = copy.deepcopy(doc)
            with patch('Quotation_KEKOREA.agent.extractor.extract_trade_data', return_value=new_doc):
                at.text_area[0].set_value('Create a PI. Cell quantity 10 PCS at USD 1 per PCS. No discount.').run(timeout=20)
                at.button[0].click().run(timeout=20)
            self.assertFalse(at.exception)
            delivery = next(entry for entry in at.text_input if entry.label.startswith('Delivery terms'))
            self.assertEqual(delivery.value, '')
            self.assertTrue(pdf_button().disabled)
