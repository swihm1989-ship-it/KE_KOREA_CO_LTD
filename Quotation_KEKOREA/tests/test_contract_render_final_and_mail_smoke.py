"""Include existing isolated orchestration regression cases in mandatory contract CI.

These cases exercise the REAL shared legacy FINAL PI PDF renderer with fake
counterparties and a temporary synthetic stamp, without production credentials.
They also exercise Resend HTTPS payload shape using a mocked network opener.
"""
import unittest
from Quotation_KEKOREA.orchestration.router import classify

# unittest discovers imported TestCase classes exposed by this module.
# The canonical test implementations remain in their orchestration modules.
from Quotation_KEKOREA.orchestration.tests.test_trade_final_export import (
    TradeReviewTests as FinalTradePdfTests,
)
from Quotation_KEKOREA.orchestration.tests.test_trade_incomplete_final import (
    IncompleteFinalTests as IncompleteFinalPdfTests,
)
from Quotation_KEKOREA.orchestration.tests.test_render_https_mail_transport import (
    HttpsTransportTests as ApprovedHttpsAttachmentTests,
)


class CombinedInvoicePackingSmokeTests(unittest.TestCase):
    def test_cipl_request_routes_to_both_ci_and_pl(self):
        self.assertEqual(classify("", "", requested=["CIPL"]), ["CI", "PL"])
        self.assertEqual(classify("Please issue CI/PL", ""), ["CI", "PL"])

    def test_cipl_never_becomes_unrecognized_document_format(self):
        self.assertEqual(classify("", "", requested=["PI", "CIPL", "PO"]),
                         ["PI", "CI", "PL", "PO"])


if __name__ == "__main__":
    unittest.main()
