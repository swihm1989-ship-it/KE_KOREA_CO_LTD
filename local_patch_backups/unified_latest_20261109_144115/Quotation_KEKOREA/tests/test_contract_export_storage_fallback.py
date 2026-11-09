"""Storage failure must not discard an already-rendered contract file."""
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests
from Quotation_KEKOREA.contracts.repository import ContractRepositoryError


class ExportStorageFallbackTests(ThreeBoxUiTests):
    def test_draft_pdf_survives_private_storage_failure_in_session(self):
        self.run_app()
        with patch.object(self.repo, 'save_export', side_effect=ContractRepositoryError('simulated DB failure')):
            self.button('검토용 초안 PDF').click()
            self.run_app()
        self.assertEqual(self.repo.exports, [])
        self.assertEqual(self.repo.files, {})
        self.assertNotIn('contract_output_draft_sample_1_pdf', self.at.session_state)
        recovered = self.at.session_state['contract_unsaved_output_draft_sample_1_pdf']
        self.assertTrue(recovered['content'].startswith(b'%PDF-'))

    def test_pdf_renderer_failure_does_not_offer_local_file(self):
        self.run_app()
        with patch('Quotation_KEKOREA.contracts.ui.export_draft', side_effect=ValueError('simulated render error')):
            self.button('검토용 초안 PDF').click()
            self.run_app()
        self.assertNotIn('contract_unsaved_output_draft_sample_1_pdf', self.at.session_state)
        self.assertFalse(self.repo.exports)

    def test_final_still_blocked_with_missing_required_terms(self):
        self.run_app()
        self.assertTrue(self.button('최종 계약서 PDF').disabled)
        self.assertNotIn('contract_unsaved_output_final_sample_1_pdf', self.at.session_state)


if __name__ == '__main__':
    unittest.main()
