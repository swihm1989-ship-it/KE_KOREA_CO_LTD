"""Regression checks for explicit previous-revision note recovery."""
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.tests import test_contract_three_box_ui as fixture


class PreviousRevisionNoteRecoveryTests(unittest.TestCase):
    setUp = fixture.ThreeBoxUiTests.setUp
    run_app = fixture.ThreeBoxUiTests.run_app

    def test_previous_note_can_be_explicitly_recovered_and_requested(self):
        self.repo.save_annotation(dict(id='prior', contract_id='sample', sentence_id='s1',
            base_revision=0, status='note', instruction='기존 메모 다시 확인'))
        self.run_app()
        button = self.at.button(key='contract_batch_request_sample_1')
        self.assertTrue(button.disabled)
        self.at.button(key='contract_restore_note_sample_1_s1').click()
        self.run_app()
        self.assertEqual(self.at.text_area(key='contract_note_sample_1_s1').value,
                         '기존 메모 다시 확인')
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        self.assertTrue(self.at.button(key='contract_batch_request_sample_1').disabled)
        self.at.checkbox(key='contract_ai_consent_sample').check()
        self.run_app()
        self.assertFalse(self.at.button(key='contract_batch_request_sample_1').disabled)

    def test_deleted_sentence_note_is_not_restorable(self):
        self.repo.save_annotation(dict(id='prior', contract_id='sample',
            sentence_id='deleted_sentence', base_revision=0,
            status='note', instruction='삭제된 문장 메모'))
        self.run_app()
        self.assertFalse(any('contract_restore_note_' in str(b.key)
                             for b in self.at.button))

    def test_previous_note_is_not_implicitly_approved(self):
        self.repo.save_annotation(dict(id='prior', contract_id='sample', sentence_id='s1',
            base_revision=0, status='note', instruction='이전 메모'))
        self.run_app()
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        self.assertTrue(self.at.button(key='contract_batch_request_sample_1').disabled)
