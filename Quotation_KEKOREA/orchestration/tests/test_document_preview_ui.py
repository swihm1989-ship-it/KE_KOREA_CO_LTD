"""Original deterministic document previews remain testable, sidebar page hidden."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui" / "streamlit_page.py"


class PreviewUITest(unittest.TestCase):
    def test_trade_demo_preview_is_draft(self):
        from Quotation_KEKOREA.orchestration.workflows.document_preview import build_preview
        doc = {
            "document_type": "PI", "product_family": "solar_cell", "currency": "USD",
            "document_number": "DRAFT", "seller": {"legal_name": "KE KOREA CO. LTD", "address": "Example Street"},
            "buyer": {"legal_name": "Demo Buyer LLC", "address": "Example Street"},
            "incoterms": "EXW Seoul", "payment_terms": "To confirm",
            "items": [{"product_name": "M10 test cell", "quantity": "100",
                       "unit": "PCS", "unit_price": "0.2", "price_basis": "PCS",
                       "price_source": "demo"}],
        }
        preview = build_preview("PI", doc)
        self.assertEqual(preview.watermark, "DRAFT - NOT FOR ISSUE")
        self.assertFalse(preview.final)
        self.assertTrue(preview.items)

    def test_empty_contract_is_not_approved(self):
        from Quotation_KEKOREA.orchestration.workflows.document_preview import build_preview
        preview = build_preview("CONTRACT", {
            "contract_id": "DRAFT-DEMO", "contract_type": "sale", "language": "ko",
            "revision": 1, "parties": [], "terms": [], "clauses": [], "issues": [],
        })
        self.assertTrue(preview.blockers)
        self.assertFalse(preview.final)

    def test_sidebar_preview_option_hidden(self):
        with patch("Quotation_KEKOREA.orchestration.security.auth_gate.require_authentication",
                   return_value="synthetic@example.test"), patch(
            "Quotation_KEKOREA.orchestration.ui.market_news_page._cached_news",
            return_value=([], None)
        ):
            app = AppTest.from_file(str(UI)).run()
        self.assertNotIn("문서 초안 미리보기", list(app.radio[0].options))


if __name__ == "__main__":
    unittest.main()
