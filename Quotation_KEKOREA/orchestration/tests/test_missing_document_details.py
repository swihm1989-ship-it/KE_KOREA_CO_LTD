"""MASTER must ask for every missing visible field before branded output."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.agent.review_fields import missing_review_fields
from Quotation_KEKOREA.orchestration.workflows.intake_followups import apply_answer, missing_fields


def complete_pi():
    party = {"legal_name": "SYNTHETIC COMPANY LTD", "address": "Seoul, Korea",
             "contact": "N/A", "phone": "N/A", "email": "N/A"}
    return {"document_type": "PI", "product_family": "solar_cell", "document_number": "DRAFT",
            "buyer": dict(party), "seller": dict(party, legal_name="KE KOREA CO. LTD"), "currency": "USD",
            "incoterms": "EXW Seoul", "payment_terms": "T/T in advance", "ship_to": "N/A",
            "shipment_reference": "N/A", "country_of_origin": "Korea",
            "items": [{"product_name": "Synthetic M10 cell", "quantity": "0", "unit": "PCS",
                       "unit_price": "0.20", "price_basis": "PCS", "discount_percent": "0"}]}


class MissingDetailsTests(unittest.TestCase):
    def test_screenshot_contact_placeholders_are_all_requested(self):
        doc = complete_pi()
        for field in ("phone", "email", "contact"):
            doc["seller"][field] = "Not provided"
        doc["buyer"]["email"] = "Not provided"
        expected = {"seller.phone", "seller.email", "seller.contact", "buyer.email"}
        self.assertEqual({f.key for f in missing_fields({"PI": doc})}, expected)

    def test_required_placeholder_is_missing_but_optional_explicit_na_is_valid(self):
        for value in ("Not provided", "TBD", "TO_BE_CONFIRMED", "unknown", "N/A"):
            with self.subTest(value=value):
                doc = complete_pi()
                doc["buyer"]["address"] = value
                self.assertIn("buyer.address", {f.key for f in missing_fields({"PI": doc})})
        self.assertEqual(missing_fields({"PI": complete_pi()}), ())

    def test_each_visible_legacy_gap_has_a_master_input_key(self):
        doc = complete_pi()
        doc.update(ship_to="", shipment_reference="", country_of_origin="")
        doc["items"].append(dict(doc["items"][0], discount_percent=""))
        keys = {f.key for f in missing_fields({"PI": doc})}
        self.assertTrue({"ship_to", "shipment_reference", "country_of_origin",
                         "item.1.discount_percent"}.issubset(keys), keys)
        updated = apply_answer({"PI": doc}, "item.1.discount_percent", "0")
        self.assertEqual(updated["PI"]["items"][1]["discount_percent"], "0")
        self.assertEqual(updated["PI"]["items"][0]["quantity"], "0")

    def test_a_filled_other_document_does_not_hide_a_gap(self):
        pi = complete_pi()
        po = deepcopy(pi)
        po["document_type"] = "PO"
        po["buyer"]["email"] = ""
        self.assertIn("buyer.email", {f.key for f in missing_fields({"PI": pi, "PO": po})})

    def test_contacts_sync_to_trade_and_contract_representative_without_auto_approval(self):
        doc = complete_pi()
        bundle = {kind: dict(deepcopy(doc), document_type=kind) for kind in ("PI", "PO", "CI", "PL")}
        bundle["CONTRACT"] = {"parties": [{"roles": ["seller"], "status": "confirmed"}],
                              "clauses": [{"title": "old"}]}
        before = deepcopy(bundle)
        changed = apply_answer(bundle, "seller.contact", "SYNTHETIC SIGNER, CEO")
        self.assertEqual(bundle, before)
        for kind in ("PI", "PO", "CI", "PL"):
            self.assertEqual(changed[kind]["seller"]["contact"], "SYNTHETIC SIGNER, CEO")
        self.assertEqual(changed["CONTRACT"]["parties"][0]["representative"], "SYNTHETIC SIGNER, CEO")
        self.assertEqual(changed["CONTRACT"]["parties"][0]["status"], "suggested")
        self.assertEqual(changed["CONTRACT"]["clauses"], [])

    def test_po_contact_edit_follows_company_identity_without_overwriting_customer(self):
        pi = complete_pi()
        pi["buyer"]["legal_name"] = "SYNTHETIC CUSTOMER LTD"
        po = deepcopy(pi)
        po.update(document_type="PO", buyer=deepcopy(pi["seller"]),
                  seller=dict(deepcopy(pi["seller"]), legal_name="SYNTHETIC SUPPLIER LTD"))
        source = {"PI": pi, "PO": po, "CONTRACT": {"parties": [
            {"roles": ["buyer"], "legal_name": "SYNTHETIC CUSTOMER LTD", "email": "customer@example.com",
             "status": "confirmed"},
            {"roles": ["seller"], "legal_name": "KE KOREA CO. LTD", "status": "confirmed"}],
            "clauses": [{"title": "old"}]}}
        changed = apply_answer(source, "PO.buyer.email", "company@example.com")
        self.assertEqual(changed["PO"]["buyer"]["email"], "company@example.com")
        self.assertEqual(changed["PI"]["seller"]["email"], "company@example.com")
        self.assertEqual(changed["PI"]["buyer"]["email"], "N/A")
        self.assertEqual(changed["PO"]["seller"]["email"], "N/A")
        self.assertEqual(changed["CONTRACT"]["parties"][0]["email"], "customer@example.com")
        self.assertEqual(changed["CONTRACT"]["parties"][0]["status"], "confirmed")
        self.assertEqual(changed["CONTRACT"]["parties"][1]["email"], "company@example.com")
        self.assertEqual(changed["CONTRACT"]["parties"][1]["status"], "suggested")

    def test_extracted_contacts_are_preserved_in_trade_candidate(self):
        from Quotation_KEKOREA.orchestration.workflows.ai_intake import make_trade_candidate
        analysis = {"contract_type": "sale", "terms": [], "parties": [
            {"roles": ["seller"], "legal_name": "Synthetic Seller", "address": "Seoul",
             "representative": "SYNTHETIC SIGNER", "phone": "+82-2-0000-0000",
             "email": "seller@example.com"}]}
        party = make_trade_candidate("PI", analysis)["seller"]
        self.assertEqual(party["contact"], "SYNTHETIC SIGNER")
        self.assertEqual(party["phone"], "+82-2-0000-0000")
        self.assertEqual(party["email"], "seller@example.com")

    def test_branded_renderer_rejects_unreviewed_contact_before_seal_fetch(self):
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports as module
        doc = complete_pi()
        doc["buyer"]["email"] = "Not provided"
        with patch.object(module, "resolve_company_seal") as seal:
            with self.assertRaisesRegex(ValueError, "누락 정보"):
                module.render_master_trade_draft("PI", doc, {})
            seal.assert_not_called()


    def test_entered_contacts_reach_original_pdf_html_and_incomplete_pdf(self):
        from io import BytesIO
        from pathlib import Path
        import pymupdf
        from PIL import Image
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports as module
        doc = complete_pi()
        doc["seller"].update(phone="+82-2-0000-0000", email="seller@example.com",
                             contact="SYNTHETIC SIGNER, CEO")
        doc["buyer"]["email"] = "buyer@example.com"
        image = BytesIO()
        Image.new("RGB", (2, 2), "red").save(image, format="PNG")
        env = {"KEKOREA_USD_" + key: "SYNTHETIC " + key for key in module.BANK_KEYS}
        with patch.object(module, "resolve_company_seal", return_value=(
                Path("/not-present/synthetic-seal.png"), image.getvalue(), None)):
            files = module.render_master_trade_draft("PI", doc, env)
        for data in (files["pdf"], module.render_incomplete_trade_pdf("PI", doc)["pdf"]):
            with pymupdf.open(stream=data["content"], filetype="pdf") as pdf:
                text = "\n".join(page.get_text() for page in pdf)
            for value in ("seller@example.com", "buyer@example.com", "SYNTHETIC SIGNER"):
                self.assertIn(value, text)
        self.assertIn(b"seller@example.com", files["html"]["content"])

    def test_contract_country_remains_visible_and_contract_gaps_stay_editable(self):
        from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _shared_current
        candidates = {"PI": complete_pi(), "CONTRACT": {"parties": [
            {"roles": ["buyer"], "legal_name": "", "address": "", "country": "China"},
            {"roles": ["seller"], "legal_name": "KE KOREA CO. LTD", "address": "Seoul, Korea", "country": "Korea"}]}}
        candidates["PO"] = dict(deepcopy(candidates["PI"]), document_type="PO")
        candidates["PO"]["buyer"]["legal_name"] = "KE KOREA CO. LTD"
        self.assertEqual(_shared_current(candidates, "buyer.country"), "China")
        self.assertEqual(_shared_current(candidates, "seller.country"), "Korea")
        self.assertEqual(_shared_current(candidates, "buyer.legal_name"), "SYNTHETIC COMPANY LTD")
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string(
            "from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _render_single_editor\n"
            + "_render_single_editor('contract-gaps', " + repr(candidates) + ")").run()
        app.session_state["ai_intake_candidates"] = ("contract-gaps", candidates)
        app.button(key="ai_intake_shared_contract-gap_buyer_legal_name_apply_to_missing").click().run()
        self.assertFalse(app.exception)
        party = app.session_state["ai_intake_candidates"][1]["CONTRACT"]["parties"][0]
        self.assertEqual(party["legal_name"], "SYNTHETIC COMPANY LTD")
        self.assertEqual(party["status"], "suggested")
        self.assertEqual(app.session_state["ai_intake_candidates"][1]["PO"]["buyer"]["legal_name"],
                         "KE KOREA CO. LTD")

    def test_workflow_reload_preserves_current_rag_draft_api(self):
        import importlib
        from inspect import signature
        from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _current_ai_workflow
        from Quotation_KEKOREA.orchestration.workflows import ai_intake
        with patch.object(ai_intake, "AI_WORKFLOW_REVISION", "prior-release"), patch(
                "importlib.reload", wraps=importlib.reload) as reload:
            current = _current_ai_workflow()
            self.assertIn("use_library", signature(current.generate_contract_draft).parameters)
            reload.assert_called_once_with(ai_intake)

    def test_old_editor_module_is_reloaded_even_if_signature_is_compatible(self):
        from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _current_intake_followups
        from Quotation_KEKOREA.orchestration.workflows import intake_followups
        import importlib
        with patch.object(intake_followups, "FOLLOWUP_REVISION", "prior-release"), patch(
                "importlib.reload", wraps=importlib.reload) as reload:
            module = _current_intake_followups()
            self.assertEqual(module.FOLLOWUP_REVISION, "visible-document-fields-20261113-v1")
            reload.assert_called_once_with(intake_followups)


class MissingDetailsUiTests(unittest.TestCase):
    def test_later_document_gaps_and_extra_rows_have_empty_editable_inputs(self):
        from streamlit.testing.v1 import AppTest
        pi = complete_pi()
        ci = deepcopy(pi)
        ci["document_type"] = "CI"
        ci["buyer"]["email"] = "Not provided"
        ci["items"].append(dict(ci["items"][0], discount_percent=""))
        candidates = {"PI": pi, "CI": ci}
        app = AppTest.from_string(
            "from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _render_single_editor\n"
            + "_render_single_editor('multi-document', " + repr(candidates) + ")").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key="ai_intake_shared_multi-docume_buyer_email").value, "")
        discount = app.text_input(key="ai_intake_shared_multi-docume_item_1_discount_percent")
        self.assertEqual(discount.value, "")
        app.session_state["ai_intake_candidates"] = ("multi-document", candidates)
        discount.set_value("0").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["ai_intake_candidates"][1]["CI"]["items"][1]["discount_percent"], "0")
        self.assertEqual(len(app.session_state["ai_intake_candidates"][1]["PI"]["items"]), 1)

    def test_different_po_and_pi_companies_have_separate_contact_inputs(self):
        from streamlit.testing.v1 import AppTest
        pi = complete_pi()
        pi["buyer"]["legal_name"] = "CUSTOMER LTD"
        po = deepcopy(pi)
        po.update(document_type="PO", buyer=dict(pi["buyer"], legal_name="KE KOREA CO. LTD"))
        candidates = {"PI": pi, "PO": po}
        app = AppTest.from_string(
            "from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _render_single_editor\n"
            + "_render_single_editor('distinct-contacts', " + repr(candidates) + ")").run()
        self.assertFalse(app.exception)
        self.assertEqual(len([w for w in app.text_input if "Buyer · 이메일" in w.label]), 2)
        app.session_state["ai_intake_candidates"] = ("distinct-contacts", candidates)
        next(w for w in app.text_input if "PO · Buyer · 이메일" in w.label).set_value("company@example.com").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["ai_intake_candidates"][1]["PO"]["buyer"]["email"], "company@example.com")
        self.assertEqual(app.session_state["ai_intake_candidates"][1]["PI"]["buyer"]["email"], "N/A")

    def test_contacts_are_editable_persist_and_revoke_old_downloads(self):
        from streamlit.testing.v1 import AppTest
        from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _render_single_editor
        # Render the actual shared editor with synthetic in-memory facts only.
        app = AppTest.from_string(
            "from Quotation_KEKOREA.orchestration.ui.ai_intake_page import _render_single_editor\n"
            "from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi\n"
            "_render_single_editor('synthetic-details', {'PI': complete_pi()})").run()
        self.assertFalse(app.exception)
        for role in ("buyer", "seller"):
            for field in ("contact", "phone", "email"):
                key = "ai_intake_shared_synthetic-de_" + role + "_" + field
                self.assertEqual(app.text_input(key=key).value, "N/A")
        app.session_state["ai_intake_candidates"] = ("synthetic-details", {"PI": complete_pi()})
        app.session_state["master_legacy_files"] = ("old", {}, {})
        app.session_state["ai_intake_drafts"] = ("old", {})
        app.text_input(key="ai_intake_shared_synthetic-de_seller_email").set_value("seller@example.com").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["ai_intake_candidates"][1]["PI"]["seller"]["email"],
                         "seller@example.com")
        self.assertNotIn("master_legacy_files", app.session_state)
        self.assertNotIn("ai_intake_drafts", app.session_state)


if __name__ == "__main__":
    unittest.main()
