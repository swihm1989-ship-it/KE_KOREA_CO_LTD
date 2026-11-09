"""Contract UI orchestration must not alter the existing revision engines."""
from copy import deepcopy
from io import BytesIO
import unittest

import fitz
from docx import Document

from Quotation_KEKOREA.contracts.models import new_snapshot


def example_snapshot():
    snapshot = dict(new_snapshot('sample', 'sale', 'ko'), title='검토 계약', revision=4)
    snapshot['clauses'] = [{'id': 'c1', 'title': '1. 범위', 'order': 1,
                            'sentences': [{'id': 's1', 'text': '첫 번째 계약 문장입니다.'},
                                          {'id': 's2', 'text': '두 번째 계약 문장입니다.'}]}]
    snapshot['issues'] = [{'id': 'i1', 'code': 'payment', 'severity': 'block',
                           'message': 'Confirm payment terms before signing.'}]
    return snapshot


def note(note_id='n1', sentence='s1', revision=4, instruction='간결하게 수정'):
    return {'id': note_id, 'contract_id': 'sample', 'sentence_id': sentence,
            'base_revision': revision, 'status': 'note', 'instruction': instruction}


class WorkspaceActionsTests(unittest.TestCase):
    def test_notes_are_revision_bound_and_superseded_notes_are_excluded(self):
        from Quotation_KEKOREA.contracts.workspace import collect_notes
        snapshot = example_snapshot()
        annotations = [note('new'), note('old'), note('stale', revision=3),
                       note('gone', sentence='deleted'), dict(note('other'), contract_id='other')]
        before = deepcopy(annotations)
        result = collect_notes(snapshot, annotations)
        self.assertEqual([n['id'] for n in result['notes']], ['new'])
        self.assertEqual(len(result['excluded']), 4)
        self.assertEqual(annotations, before)

    def test_applied_notes_are_never_reused(self):
        from Quotation_KEKOREA.contracts.workspace import collect_notes
        snapshot = example_snapshot()
        snapshot['applied_note_ids'] = ['n1']
        self.assertEqual(collect_notes(snapshot, [note()])['notes'], [])

    def test_batch_proposals_use_one_base_revision_without_mutating_snapshot(self):
        from Quotation_KEKOREA.contracts.workspace import build_batch_proposal
        snapshot = example_snapshot()
        before = deepcopy(snapshot)
        calls = []
        def proposer(current, sentence_id, instruction, *, env):
            calls.append((current['revision'], sentence_id))
            sentence = next(s for s in current['clauses'][0]['sentences'] if s['id'] == sentence_id)
            return {'changes': [{'id': sentence_id, 'sentence_id': sentence_id,
                                 'original_text': sentence['text'], 'proposed_text': instruction}], 'issues': []}
        result = build_batch_proposal(snapshot, [note(), note('n2', 's2')], proposer=proposer, env={})
        self.assertEqual(calls, [(4, 's1'), (4, 's2')])
        self.assertEqual(result['base_revision'], 4)
        self.assertEqual(result['note_ids'], ['n1', 'n2'])
        self.assertEqual(len(result['changes']), 2)
        self.assertEqual(snapshot, before)

    def test_conflicting_related_changes_reject_whole_batch(self):
        from Quotation_KEKOREA.contracts.workspace import build_batch_proposal
        snapshot = example_snapshot()
        def proposer(current, sentence_id, instruction, *, env):
            return {'changes': [{'id': 'same', 'sentence_id': 's1',
                                 'original_text': current['clauses'][0]['sentences'][0]['text'],
                                 'proposed_text': sentence_id}], 'issues': []}
        with self.assertRaisesRegex(ValueError, '충돌'):
            build_batch_proposal(snapshot, [note(), note('n2', 's2')], proposer=proposer, env={})
        self.assertEqual(snapshot['revision'], 4)

    def test_batch_rejects_stale_notes_before_any_ai_call(self):
        from Quotation_KEKOREA.contracts.workspace import build_batch_proposal
        def no_call(*args, **kwargs):
            self.fail('stale notes must not invoke AI')
        with self.assertRaises(ValueError):
            build_batch_proposal(example_snapshot(), [note(revision=1)], proposer=no_call, env={})

    def test_draft_has_only_contract_content_and_no_signature_page(self):
        from Quotation_KEKOREA.contracts.draft_exports import export_draft
        snapshot = example_snapshot()
        before = deepcopy(snapshot)
        outputs = export_draft(snapshot, env={})
        document = Document(BytesIO(outputs['docx']['content']))
        text = '\n'.join(p.text for p in document.paragraphs)
        self.assertIn('DRAFT', document.sections[0].header.paragraphs[0].text)
        # DRAFT preserves exact sentences; unrelated omissions stay in the appendix.
        self.assertIn('첫 번째 계약 문장입니다.', text)
        self.assertIn('두 번째 계약 문장입니다.', text)
        self.assertNotIn('[확인 필요] 첫 번째 계약 문장입니다.', text)
        self.assertNotIn('[확인 필요] 두 번째 계약 문장입니다.', text)
        self.assertNotIn('[필수 확인]', text)
        self.assertNotIn('미확정 사항', text)
        self.assertNotIn('[미확정 원문]', text)
        self.assertNotIn('By: ___', text)
        with fitz.open(stream=outputs['pdf']['content'], filetype='pdf') as pdf:
            for page in pdf:
                self.assertIn('DRAFT', page.get_text())
            self.assertNotIn('미확정 사항', ''.join(p.get_text() for p in pdf))
        self.assertIn('-DRAFT-', outputs['pdf']['filename'])
        self.assertEqual(snapshot, before)

    def test_empty_draft_cannot_be_downloaded(self):
        from Quotation_KEKOREA.contracts.draft_exports import export_draft
        with self.assertRaises(ValueError):
            export_draft(new_snapshot('empty', 'sale', 'ko'), env={})

    def test_english_draft_does_not_leak_review_evidence_in_pdf(self):
        from Quotation_KEKOREA.contracts.draft_exports import export_draft
        snapshot = example_snapshot()
        snapshot['language'] = 'en'
        output = export_draft(snapshot, formats=('pdf',), env={})['pdf']['content']
        with fitz.open(stream=output, filetype='pdf') as pdf:
            text = '\n'.join(page.get_text() for page in pdf)
        self.assertNotIn('계약일 또는 효력 발생 기준', text)
        self.assertIn('첫 번째 계약 문장입니다.', text)


class ReviewCardsTests(unittest.TestCase):
    def test_cards_dedupe_only_presentation_and_use_korean_labels(self):
        from Quotation_KEKOREA.contracts.review_summary import review_cards
        issues = [dict(example_snapshot()['issues'][0]), dict(example_snapshot()['issues'][0])]
        original = deepcopy(issues)
        cards = review_cards(issues, language='ko')
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['count'], 2)
        self.assertIn(cards[0]['kind'], ['필수 확인', '권장 확인', '법률 검토 권장', '초안에 TBD 허용'])
        self.assertNotIn('Confirm payment', cards[0]['summary'])
        self.assertEqual(issues, original)

    def test_detail_and_legal_classification_never_changes_severity(self):
        from Quotation_KEKOREA.contracts.review_summary import review_cards
        issues = [{'key': 'buyer.address', 'code': 'missing_party_detail', 'severity': 'block'},
                  {'key': 'governing_law', 'code': 'missing_term', 'severity': 'block'}]
        cards = review_cards(issues)
        self.assertEqual({c['kind'] for c in cards}, {'초안에 TBD 허용', '법률 검토 권장'})
        self.assertTrue(all(i['severity'] == 'block' for i in issues))

