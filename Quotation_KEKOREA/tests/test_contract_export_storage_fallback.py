"""Storage failure must not discard an already-rendered contract file."""
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests
from Quotation_KEKOREA.contracts.repository import ContractRepositoryError


class ExportStorageFallbackTests(ThreeBoxUiTests):
    def test_draft_pdf_does_not_contact_private_storage(self):
        with patch.object(self.repo, 'save_export', side_effect=ContractRepositoryError('simulated DB failure')):
            self.run_app()
        output = self.at.session_state['contract_direct_draft_sample']['outputs']['pdf']
        self.assertTrue(output['content'].startswith(b'%PDF-'))
        self.assertEqual(self.repo.exports, [])
        self.assertEqual(self.repo.files, {})

    def test_pdf_renderer_failure_does_not_offer_stale_file(self):
        with patch('Quotation_KEKOREA.contracts.ui.export_draft', side_effect=ValueError('simulated render error')):
            self.run_app()
        self.assertNotIn('contract_direct_draft_sample', self.at.session_state)
        self.assertFalse(self.repo.exports)

    def test_final_still_blocked_without_document_approval(self):
        self.run_app()
        self.assertTrue(self.button('최종 계약서 PDF').disabled)
        self.assertNotIn('contract_unsaved_output_final_sample_1_pdf', self.at.session_state)


if __name__ == '__main__':
    unittest.main()
