"""PDF filenames are descriptive, nullable and never used for uniqueness."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, patch

from Quotation_KEKOREA.orchestration.workflows.pdf_filename import pdf_filename
from Quotation_KEKOREA.orchestration.workflows import pdf_archive


class PdfFilenameTests(TestCase):
    def setUp(self):
        self.pi={
            "document_number": "PI-2026-11",
            "buyer": {"legal_name": "GLOW INTERNATIONAL"},
            "seller": {"legal_name": "KE KOREA CO. LTD"},
            "items": [{"product_name": "M10 PERC cell", "quantity": "1000000",
                       "unit": "PCS"}],
        }

    def test_pi_filename_with_all_fields(self):
        self.assertEqual(pdf_filename("PI", self.pi),
                         "PI_PI-2026-11_KE-KOREA_GLOW INTERNATIONAL_M10 PERC cell(1000000 PCS).pdf")

    def test_po_uses_supplier_and_ci_pl_same_pattern(self):
        po=deepcopy(self.pi)
        po["buyer"]={"legal_name": "KE KOREA CO. LTD"}
        po["seller"]={"legal_name": "ECLADO"}
        self.assertTrue(pdf_filename("PO", po).startswith("PO_PI-2026-11_KE-KOREA_ECLADO_"))
        for kind in ("CI","PL"):
            self.assertTrue(pdf_filename(kind, self.pi).startswith(kind+"_PI-2026-11_KE-KOREA_"))

    def test_all_optional_fields_missing_produces_pdf(self):
        for kind in ("PI","PO","CI","PL","CONTRACT"):
            self.assertEqual(pdf_filename(kind, {}),kind+"_KE-KOREA.pdf")
        self.assertEqual(pdf_filename("PI",{"document_number":"DRAFT","items":[{}]}),
                         "PI_KE-KOREA.pdf")

    def test_missing_product_quantity_and_duplicate_number_are_allowed(self):
        doc=deepcopy(self.pi)
        doc["items"]=[{"product_name":"M10 PERC cell"}]
        self.assertEqual(pdf_filename("PI",doc),
                         "PI_PI-2026-11_KE-KOREA_GLOW INTERNATIONAL_M10 PERC cell.pdf")
        self.assertEqual(pdf_filename("PI",self.pi),pdf_filename("PI",deepcopy(self.pi)))
        doc["items"]=[{"product_name":"M10 PERC cell","quantity":0,"unit":"PCS"}]
        self.assertIn("M10 PERC cell(0 PCS)",pdf_filename("PI",doc))

    def test_unsafe_path_components_are_sanitized(self):
        doc=deepcopy(self.pi)
        doc["document_number"]="../../2026\\A:*?"
        doc["buyer"]["legal_name"]="Example/Buyer"
        result=pdf_filename("PI",doc)
        self.assertNotIn("/",result)
        self.assertNotIn("\\",result)
        self.assertTrue(result.endswith(".pdf"))

    def test_storage_remains_unique_for_same_document_number(self):
        repo=MagicMock()
        with patch.object(pdf_archive,"_repo",return_value=repo):
            first=pdf_archive.archive_pdf({}, "owner@example.test","PI","final",
                                          {"content":b"%PDF-1.4\nA"},self.pi)
            second=pdf_archive.archive_pdf({}, "owner@example.test","PI","final",
                                           {"content":b"%PDF-1.4\nB"},self.pi)
        self.assertEqual(first["filename"],second["filename"])
        self.assertNotEqual(first["id"],second["id"])
        self.assertNotEqual(first["storage_path"],second["storage_path"])
