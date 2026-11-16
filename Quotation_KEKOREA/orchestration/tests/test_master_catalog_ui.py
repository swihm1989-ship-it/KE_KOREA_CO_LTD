"""MASTER Streamlit session uses the legacy ECLADO catalog, with no live network."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.orchestration.ui import ai_intake_page
from Quotation_KEKOREA.orchestration.tests.test_legacy_catalog_bridge import (
    CATALOG, trade,
)

_SOURCE = """import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _remember_candidate_bundle
if 'ai_intake_candidates' not in st.session_state:
    _remember_candidate_bundle('synthetic-master', DATA, replace_editor=True)
st.write('catalog state:', st.session_state.get('master_eclado_catalog_status'))
""".replace("DATA", "None")


class MasterCatalogUiTests(unittest.TestCase):
    def app(self, doc, env):
        source = _SOURCE.replace("None", repr(doc))
        with (patch.object(ai_intake_page, 'document_export_env', return_value=env),
              patch.object(ai_intake_page, '_cached_master_eclado_catalog', return_value=CATALOG)
              as catalog_loader):
            app = AppTest.from_string(source, default_timeout=25).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app, catalog_loader

    def test_master_applies_legacy_usd_and_krw_prices_before_pdf(self):
        from Quotation_KEKOREA.orchestration.workflows.document_assets import EXPECTED_PROJECT
        env = {"SUPABASE_URL": "https://" + EXPECTED_PROJECT + ".supabase.co",
               "SUPABASE_SECRET_KEY": "TEST-ONLY-SERVER-KEY"}
        data = {
            "PI": trade("PI"),
            "PO": trade("PO", buyer="KE KOREA CO. LTD",
                        seller="ECLADO", price="12.50"),
        }
        app, loader = self.app(data, env)
        loader.assert_called_once()
        result = app.session_state['ai_intake_candidates'][1]
        self.assertEqual(result['PI']['currency'], 'USD')
        self.assertEqual(result['PI']['items'][0]['unit_price'], '12.50')
        self.assertEqual(result['PO']['currency'], 'KRW')
        self.assertEqual(result['PO']['items'][0]['unit_price'], '1000')
        self.assertEqual(app.session_state['master_eclado_catalog_status'], 'connected')

    def test_no_secrets_preserves_user_trade_price_without_network(self):
        app, loader = self.app({"PI": trade("PI", price="19.99")}, {})
        loader.assert_not_called()
        result = app.session_state['ai_intake_candidates'][1]
        self.assertEqual(result['PI']['items'][0]['unit_price'], '19.99')
        self.assertEqual(app.session_state['master_eclado_catalog_status'], 'not_configured')


if __name__ == '__main__':
    unittest.main()
