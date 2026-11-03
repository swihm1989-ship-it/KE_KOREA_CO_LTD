"""Product annotations must resolve prices in the actual review screen."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_product_matching import PRODUCTS
from Quotation_KEKOREA.tests.test_review_fields import complete_draft


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Streamlit is not installed')
class ProductMatchingUiTests(unittest.TestCase):
    def test_annotations_load_prices_without_bypassing_product_confirmation(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / 'app.py'
        catalog = dict(products=PRODUCTS, purchase_prices=[dict(product_id='cream50',
                       supplier_key='ECLADO', currency='KRW', unit_price='1000')])
        with patch('Quotation_KEKOREA.agent.extractor.load_env', return_value={'OPENAI_API_KEY': 'test'}), \
             patch('Quotation_KEKOREA.agent.pricing.load_local_seed', return_value=catalog), \
             patch('Quotation_KEKOREA.agent.branding.resolve_company_seal', return_value=(app_path, None, None)):
            for name, ready in [('Cell Memory Cream (E165)', True),
                                ('Cell Memory Cream (for dry skin)', False)]:
                with self.subTest(name=name):
                    doc = complete_draft()
                    doc.update(document_type='PO', product_family='cosmetics', currency=None)
                    doc['buyer']['legal_name'] = 'KE KOREA CO. LTD'
                    doc['seller']['legal_name'] = 'ECLADO'
                    doc['items'][0].update(product_name=name, capacity='50g', unit_price=None)
                    at = AppTest.from_file(str(app_path))
                    at.session_state['selected_document_page'] = 'PO 만들기'
                    at.session_state['trade_draft'] = doc
                    at.session_state['trade_draft_page'] = 'PO 만들기'
                    at.run(timeout=20)
                    self.assertFalse(at.exception)
                    self.assertFalse(any('unit price' in field.label for field in at.text_input))
                    metrics = {metric.label: metric.value for metric in at.metric}
                    self.assertEqual(metrics['Total amount'], 'KRW 10,000')
                    self.assertEqual(next(b for b in at.button if b.label == 'Create PDF').disabled, not ready)
                    if not ready:
                        next(c for c in at.checkbox if c.label.startswith('Confirm product annotation')).check().run(timeout=20)
                        self.assertFalse(next(b for b in at.button if b.label == 'Create PDF').disabled)
