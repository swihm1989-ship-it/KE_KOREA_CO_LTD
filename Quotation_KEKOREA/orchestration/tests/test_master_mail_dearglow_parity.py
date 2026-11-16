"""The real MASTER mail path must reuse KE KOREA buyer defaults and prices.

All names/price amounts here are synthetic fixtures except public brand labels.
No real email, live Supabase or model traffic is used.
"""
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.agent.mail_party_bridge import apply_mail_counterparties
from Quotation_KEKOREA.orchestration.workflows.legacy_catalog_bridge import reuse_legacy_catalog
from Quotation_KEKOREA.orchestration.workflows.mail_intake import (
    prepare_mail_request, queue_handoff,
)
from Quotation_KEKOREA.orchestration.tests.test_legacy_catalog_bridge import (
    CATALOG, trade,
)
from Quotation_KEKOREA.orchestration.ui import ai_intake_page
from Quotation_KEKOREA.orchestration.workflows.document_assets import EXPECTED_PROJECT


PROFILES = [
    {"company_key": "ECLADO", "legal_name": "ECLADO Co. LTD",
     "aliases": ["ECLADO", "에끌라두"], "address": "Synthetic Eclado warehouse"},
    {"company_key": "DEAR_GLOW", "legal_name": "DEAR GLOW PTE LTD",
     "aliases": ["Dear Glow", "Dearglow"], "address": "Synthetic Dear Glow office",
     "contact": "Synthetic Buyer", "email": "buyer@example.test"},
]
MAIL = (
    "메일 제목: ECLADO PO_DEARGLOW\n\n"
    "Dear David,\nPlease provide PI for below volume:\n\n[image: TEST.png]"
)


def incomplete_pi():
    doc = trade("PI", buyer="", seller="", price=None)
    doc["buyer"] = {"legal_name": "", "address": "", "email": ""}
    doc["seller"] = {"legal_name": "", "address": ""}
    doc["product_family"] = "solar_cell"  # Existing MASTER default before parity fix.
    return doc


class MasterDearGlowMailParityTests(unittest.TestCase):
    def test_body_pi_request_overrides_po_in_subject(self):
        request = prepare_mail_request("ECLADO PO_DEARGLOW",
                                       "Dear David,\nPlease provide PI for below volume:\n[image: TEST.png]")
        self.assertEqual(request.kinds, ("PI",))
        state = {}
        mail = SimpleNamespace(subject="ECLADO PO_DEARGLOW",
                               sender="Synthetic buyer <buyer@example.test>",
                               body="Please provide PI for below volume:\n[image: TEST.png]")
        queue_handoff(state, mail, requested=list(request.kinds))
        self.assertEqual(state["ai_intake_family"], "cosmetics")
        self.assertEqual(state["ai_intake_mail_source"]["sender"], mail.sender)
        self.assertFalse(state["ai_intake_consent"])

    def test_company_defaults_and_price_from_existing_legacy_components(self):
        original = incomplete_pi()
        intermediate = apply_mail_counterparties({"PI": original}, PROFILES,
                                                  instruction=MAIL)
        doc = intermediate["PI"]
        self.assertEqual(original["buyer"]["legal_name"], "")
        self.assertEqual(doc["buyer"]["legal_name"], "DEAR GLOW PTE LTD")
        self.assertEqual(doc["buyer"]["address"], "Synthetic Dear Glow office")
        self.assertEqual(doc["seller"]["legal_name"], "KE Korea Co. LTD")
        self.assertEqual(doc["product_family"], "cosmetics")
        priced = reuse_legacy_catalog(intermediate, CATALOG)["PI"]
        self.assertEqual(priced["items"][0]["unit_price"], "12.50")
        self.assertTrue(priced["items"][0]["master_price"])
        self.assertEqual(priced["currency"], "USD")

    def test_explicit_other_buyer_never_receives_dear_glow_prices(self):
        doc = incomplete_pi()
        doc["buyer"]["legal_name"] = "ANOTHER BUYER LTD"
        doc["items"][0]["unit_price"] = "19.99"
        intermediate = apply_mail_counterparties({"PI": doc}, PROFILES,
                                                   instruction=MAIL)
        priced = reuse_legacy_catalog(intermediate, CATALOG)["PI"]
        self.assertEqual(priced["buyer"]["legal_name"], "ANOTHER BUYER LTD")
        self.assertEqual(priced["items"][0]["unit_price"], "19.99")
        self.assertNotIn("12.50", str(priced))

    def test_master_session_import_uses_original_profiles_then_catalog(self):
        doc = incomplete_pi()
        source = """import streamlit as st
from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _remember_candidate_bundle
st.session_state["ai_intake_mail_source"] = {"kinds": ["PI"], "subject": "ECLADO PO_DEARGLOW"}
st.session_state["ai_intake_instruction"] = SOURCE
_remember_candidate_bundle("mail-dearglow-synthetic", {"PI": DATA}, replace_editor=True)
""".replace("SOURCE", repr(MAIL)).replace("DATA", repr(doc))
        env = {"SUPABASE_URL": "https://" + EXPECTED_PROJECT + ".supabase.co",
               "SUPABASE_SECRET_KEY": "TEST-ONLY-SERVER-KEY"}
        with (patch.object(ai_intake_page, "document_export_env", return_value=env),
              patch.object(ai_intake_page, "_cached_master_company_profiles",
                           return_value=PROFILES) as lookup,
              patch.object(ai_intake_page, "_cached_master_eclado_catalog",
                           return_value=CATALOG) as catalog):
            app = AppTest.from_string(source, default_timeout=25).run()
        self.assertFalse(app.exception, [x.message for x in app.exception])
        lookup.assert_called_once()
        catalog.assert_called_once()
        pi = app.session_state["ai_intake_candidates"][1]["PI"]
        self.assertEqual(pi["buyer"]["legal_name"], "DEAR GLOW PTE LTD")
        self.assertEqual(pi["seller"]["legal_name"], "KE Korea Co. LTD")
        self.assertEqual(pi["items"][0]["unit_price"], "12.50")
        self.assertEqual(pi["currency"], "USD")
        self.assertEqual(app.session_state["master_company_directory_status"], "connected")
        self.assertEqual(app.session_state["master_eclado_catalog_status"], "connected")

    def test_no_product_in_mail_text_stays_unpriced_without_image_bytes(self):
        doc = incomplete_pi()
        doc["items"] = [{"product_name": "", "quantity": "", "unit": "", "unit_price": None}]
        enriched = apply_mail_counterparties({"PI": doc}, PROFILES, instruction=MAIL)
        priced = reuse_legacy_catalog(enriched, CATALOG)
        self.assertIn(priced["PI"]["items"][0]["unit_price"], (None, ""))
        self.assertEqual(priced["PI"]["items"][0]["quantity"], "")


if __name__ == "__main__":
    unittest.main()
