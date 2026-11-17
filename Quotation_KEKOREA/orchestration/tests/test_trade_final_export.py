"""Actionable per-document review and explicit owner-approved FINAL exports."""
from copy import deepcopy
from io import BytesIO
import importlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.orchestration.tests.test_missing_document_details import complete_pi

MODULE='Quotation_KEKOREA.orchestration.workflows.trade_export_review'

class TradeReviewTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'Per-document export review is missing')
        self.review=importlib.import_module(MODULE)
        self.doc=complete_pi();self.doc['document_number']='PI-SYNTHETIC-001'

    def test_two_missing_fields_have_names_and_explicit_na_resolves_only_optional_values(self):
        self.doc['buyer']['email']=''
        self.doc['seller']['phone']='Not provided'
        before=deepcopy(self.doc)
        report=self.review.review_trade_document('PI',self.doc)
        self.assertEqual({row['key'] for row in report['missing']},{'buyer.email','seller.phone'})
        self.assertTrue(all(row['label'] for row in report['missing']))
        completed=self.review.review_trade_document('PI',self.doc,allow_optional_na=True)
        self.assertEqual(completed['issues'],[])
        self.assertEqual(completed['candidate']['buyer']['email'],'N/A')
        self.assertEqual(self.doc,before)

    def test_entered_zero_and_optional_na_are_complete_but_ci_origin_is_required(self):
        self.doc.update(shipment_reference='N/A',country_of_origin='N/A')
        self.doc['items'][0]['discount_percent']='0'
        self.assertEqual(self.review.review_trade_document('PI',self.doc)['issues'],[])
        ci=deepcopy(self.doc);ci['document_type']='CI'
        report=self.review.review_trade_document('CI',ci,allow_optional_na=True)
        self.assertIn('country_of_origin',{row['key'] for row in report['missing']})

    def test_historical_ai_notes_are_reported_separately_from_real_missing_fields(self):
        self.doc['missing_fields']=['Check original payment date']
        report=self.review.review_trade_document('PI',self.doc)
        self.assertEqual(report['missing'],[])
        self.assertTrue(any(row['code']=='ai_missing' for row in report['issues']))
        self.assertEqual(self.doc['missing_fields'],['Check original payment date'])

    def test_final_requires_real_number_and_correct_required_values(self):
        self.doc['document_number']='DRAFT'
        self.doc['buyer']['legal_name']='N/A'
        report=self.review.review_trade_document('PI',self.doc,final=True,allow_optional_na=True)
        self.assertIn('document_number',{row['key'] for row in report['issues']})
        self.assertIn('buyer.legal_name',{row['key'] for row in report['missing']})

    def test_final_cannot_be_approved_by_candidate_data_or_stale_hash(self):
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports as exports
        self.doc['approved']=True
        with self.assertRaisesRegex(ValueError,'승인'):
            exports.render_master_trade_final('PI',self.doc,{},approved=False)
        digest=self.review.trade_export_fingerprint('PI',self.doc,allow_optional_na=True)
        self.doc['items'][0]['unit_price']='0.25'
        with self.assertRaisesRegex(ValueError,'변경'):
            exports.render_master_trade_final('PI',self.doc,{},approved=True,expected_fingerprint=digest,allow_optional_na=True)

    def test_other_family_three_computer_parts_generate_real_final_pi_pdf(self):
        from PIL import Image
        import pymupdf
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports as exports
        pi = deepcopy(self.doc)
        pi["product_family"] = "other"
        pi["document_number"] = "PI-SYNTHETIC-HARDWARE-001"
        pi["items"] = [
            {"product_name": name, "quantity": str(qty), "unit": "PCS",
             "unit_price": str(price), "price_basis": "PCS", "discount_percent": "0"}
            for name, qty, price in (
                ("Wireless Mouse MX-200", 10, "12.00"),
                ("Mechanical Keyboard MK-400", 5, "32.50"),
                ("USB-C Hub XH-100", 2, "19.90"),
            )
        ]
        report = self.review.review_trade_document(
            "PI", pi, final=True, allow_optional_na=True)
        self.assertEqual(report["issues"], [], report["issues"])
        self.assertEqual(report["render_data"]["total"], "322.30")
        seal = BytesIO()
        Image.new("RGB", (2, 2), "red").save(seal, format="PNG")
        env = {"KEKOREA_USD_" + key: "SYNTHETIC " + key for key in exports.BANK_KEYS}
        expected = self.review.trade_export_fingerprint("PI", pi, allow_optional_na=True)
        with patch.object(exports, "resolve_company_seal",
                          return_value=(Path("/missing/seal.png"), seal.getvalue(), None)):
            files = exports.render_master_trade_final(
                "PI", pi, env, approved=True,
                expected_fingerprint=expected, allow_optional_na=True)
        self.assertTrue(files["pdf"]["content"].startswith(b"%PDF"))
        with pymupdf.open(stream=files["pdf"]["content"], filetype="pdf") as pdf:
            printed = "\n".join(page.get_text() for page in pdf)
        for product in ("Wireless Mouse MX-200", "Mechanical Keyboard MK-400",
                        "USB-C Hub XH-100"):
            self.assertIn(product, printed)
        self.assertIn("322.30", printed)

    def test_approved_final_uses_original_pdf_and_unapproved_draft_stays_draft(self):
        from PIL import Image
        import pymupdf
        from Quotation_KEKOREA.orchestration.workflows import legacy_document_exports as exports
        image=BytesIO();Image.new('RGB',(2,2),'red').save(image,format='PNG')
        env={'KEKOREA_USD_'+key:'SYNTHETIC '+key for key in exports.BANK_KEYS}
        digest=self.review.trade_export_fingerprint('PI',self.doc,allow_optional_na=True)
        with patch.object(exports,'resolve_company_seal',return_value=(Path('/not-present/seal.png'),image.getvalue(),None)):
            files=exports.render_master_trade_final('PI',self.doc,env,approved=True,expected_fingerprint=digest,allow_optional_na=True)
            draft=exports.render_master_trade_draft('PI',self.doc,env)
        self.assertTrue(files['pdf']['final']);self.assertFalse(files['pdf']['sendable'])
        self.assertIn('FINAL',files['pdf']['filename'])
        with pymupdf.open(stream=files['pdf']['content'],filetype='pdf') as pdf:
            text='\n'.join(page.get_text() for page in pdf)
        self.assertIn('PI-SYNTHETIC-001',text);self.assertNotIn('DRAFT - NOT FOR ISSUE',text)
        self.assertFalse(draft['pdf']['final'])

if __name__=='__main__':unittest.main()
