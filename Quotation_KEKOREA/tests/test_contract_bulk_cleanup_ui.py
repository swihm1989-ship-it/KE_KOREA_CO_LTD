"""Streamlit regression: optional cleanup cannot replace AI risk review."""
import unittest
from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests


class BulkCleanupUiTests(unittest.TestCase):
    setUp = ThreeBoxUiTests.setUp
    run_app = ThreeBoxUiTests.run_app

    def set_wrapped_sentence(self):
        self.repo.revisions['sample'][0]['snapshot']['clauses'][0]['sentences'][0]['text'] = (
            '[서명 전 확인: 당사자는 위반 사실을 상대방에게 서면 통지한다.]'
        )

    def test_optional_bulk_cleanup_and_existing_risk_review_visible(self):
        self.set_wrapped_sentence()
        self.run_app()
        self.assertFalse(self.at.button(
            key='contract_bulk_cleanup_sample_1').disabled)
        labels = [e.label for e in self.at.expander]
        self.assertIn('AI 핵심 위험 검토 · 필요할 때 실행', labels)
        self.assertIn('AI 일괄 문장 정리 · 서명 전 확인 문구', labels)
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)

    def test_pending_risk_preview_disables_bulk_cleanup_without_deleting_it(self):
        self.set_wrapped_sentence()
        self.at.session_state['contract_risk_preview_sample'] = {
            'revision': 1, 'sentences': {'s1': 'Risk alternative preserved'},
        }
        self.run_app()
        self.assertTrue(self.at.button(
            key='contract_bulk_cleanup_sample_1').disabled)
        self.assertEqual(
            self.at.button(key='contract_sentence_sample_s1').label,
            'Risk alternative preserved',
        )
        self.assertEqual(self.repo.records['sample']['current_revision'], 1)


if __name__ == '__main__':
    unittest.main()
