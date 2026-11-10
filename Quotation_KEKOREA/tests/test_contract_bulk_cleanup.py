"""AI bulk-cleanup suggestions must remain optional and revision-safe."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.contracts.bulk_cleanup import (
    candidate_sentences, propose_bulk_signature_cleanup,
)
from Quotation_KEKOREA.contracts.editing import apply_proposal
from Quotation_KEKOREA.tests.test_contract_workspace_actions import example_snapshot


class BulkCleanupTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = example_snapshot()
        self.snapshot['revision'] = 1
        self.snapshot['clauses'][0]['sentences'][0]['text'] = (
            '[서명 전 확인: 어느 당사자가 계약을 위반하면 상대방에게 '
            '위반 사실을 서면 통지하고 합리적인 시정 기회를 제공한다.]'
        )
        self.before = deepcopy(self.snapshot)

    def test_candidate_only_matches_full_wrappers(self):
        self.snapshot['clauses'][0]['sentences'][1]['text'] = '통상적인 품질 검증 조항.'
        self.assertEqual(len(candidate_sentences(self.snapshot)), 1)

    def test_optional_proposal_requires_separate_user_approval(self):
        updated = ('어느 당사자가 계약을 위반하면 상대방에게 위반 사실을 '
                   '서면 통지하고 합리적인 시정 기회를 제공한다.')
        sid = self.snapshot['clauses'][0]['sentences'][0]['id']
        def fake_call(instructions, payload, **kwargs):
            self.assertEqual(payload['drafting_task'], 'bulk_cleanup')
            return {'edits': [{'sentence_id': sid, 'revised_text': updated,
                               'reason': '형식적인 확인 문구 정리',
                               'needs_human_fact': False}]}
        with patch('Quotation_KEKOREA.contracts.bulk_cleanup._call', side_effect=fake_call) as mocked:
            proposal = propose_bulk_signature_cleanup(self.snapshot, env={})
        mocked.assert_called_once()
        self.assertEqual(self.snapshot, self.before)
        self.assertEqual(proposal['changes'][0]['proposed_text'], updated)
        saved = apply_proposal(self.snapshot, proposal, [proposal['changes'][0]['id']])
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(saved['clauses'][0]['sentences'][0]['text'], updated)

    def test_unresolved_money_must_not_be_silently_changed(self):
        sid = self.snapshot['clauses'][0]['sentences'][0]['id']
        self.snapshot['clauses'][0]['sentences'][0]['text'] = (
            '[서명 전 확인: 계약 가격 USD 0.225/pc, 수량 2324938 PCS를 확인한다.]'
        )
        with patch('Quotation_KEKOREA.contracts.bulk_cleanup._call',
                   return_value={'edits': [{
                       'sentence_id': sid,
                       'revised_text': '계약 가격 USD 0.22/pc, 수량 2324938 PCS이다.',
                       'needs_human_fact': False,
                   }]}):
            with self.assertRaisesRegex(ValueError, '안전하게 정리'):
                propose_bulk_signature_cleanup(self.snapshot, env={})

    def test_real_missing_fact_flag_keeps_original(self):
        sid = self.snapshot['clauses'][0]['sentences'][0]['id']
        with patch('Quotation_KEKOREA.contracts.bulk_cleanup._call',
                   return_value={'edits': [{
                       'sentence_id': sid, 'revised_text': '임의로 확정한 문장',
                       'needs_human_fact': True,
                   }]}):
            with self.assertRaisesRegex(ValueError, '안전하게 정리'):
                propose_bulk_signature_cleanup(self.snapshot, env={})

    def test_ai_cannot_edit_unrelated_sentence_or_duplicate_id(self):
        sid = self.snapshot['clauses'][0]['sentences'][0]['id']
        with patch('Quotation_KEKOREA.contracts.bulk_cleanup._call',
                   return_value={'edits': [
                       {'sentence_id': sid, 'revised_text': 'A'},
                       {'sentence_id': sid, 'revised_text': 'B'},
                   ]}):
            with self.assertRaisesRegex(ValueError, '중복되거나'):
                propose_bulk_signature_cleanup(self.snapshot, env={})


if __name__ == '__main__':
    unittest.main()
