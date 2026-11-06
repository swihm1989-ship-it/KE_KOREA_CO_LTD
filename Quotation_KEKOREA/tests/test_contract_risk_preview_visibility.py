"""Rerun-safe BOX 3 visibility of uncommitted AI risk-review edits."""
import unittest
from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests


class RiskPreviewVisibilityTests(unittest.TestCase):
    setUp = ThreeBoxUiTests.setUp
    run_app = ThreeBoxUiTests.run_app
    def test_box3_displays_changed_sentence_and_unsaved_notice(self):
        self.at.session_state['contract_risk_preview_sample'] = {
            'revision': 1, 'sentences': {'s1': '사용자가 수정한 지급 조항'}
        }
        self.run_app()
        self.assertEqual(self.at.button(key='contract_sentence_sample_s1').label,
                         '사용자가 수정한 지급 조항')
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)
        texts = [info.value for info in self.at.info]
        self.assertTrue(any('AI 위험 검토 수정안 1개' in value for value in texts))
        self.assertTrue(any('새 revision으로 저장' in value for value in texts))
        self.run_app()
        self.assertEqual(self.at.button(key='contract_sentence_sample_s1').label,
                         '사용자가 수정한 지급 조항')

    def test_outdated_preview_not_displayed_as_current(self):
        self.at.session_state['contract_risk_preview_sample'] = {
            'revision': 0, 'sentences': {'s1': '오래된 수정안'}
        }
        self.run_app()
        self.assertNotEqual(self.at.button(key='contract_sentence_sample_s1').label,
                            '오래된 수정안')
        self.assertFalse(any('AI 위험 검토 수정안 1개' in info.value for info in self.at.info))


if __name__ == '__main__':
    unittest.main()
