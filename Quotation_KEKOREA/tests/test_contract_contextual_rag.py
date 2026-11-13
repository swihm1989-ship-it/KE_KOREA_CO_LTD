"""Offline tests: no private originals leave the service role, no approvals are inferred."""
import io
import json
import unittest
import zipfile
from copy import deepcopy
from unittest.mock import patch

from Quotation_KEKOREA.contracts.contextual_rag import (
    approve_source_excerpts, approved_neighbor_context, build_comparison_candidates,
    compare_approved_clauses, index_private_original, private_index,
)
from Quotation_KEKOREA.contracts.library import (
    read_manifest, register_sample, search_library_topics,
)
from Quotation_KEKOREA.tests.test_contract_library import MemoryLibrary, tiny_docx


def make_docx(sections):
    stream = io.BytesIO()
    body = ''.join('<w:p><w:r><w:t>' + text + '</w:t></w:r></w:p>'
                   for text in sections)
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr(
            'word/document.xml',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body>'
            + body + '</w:body></w:document>',
        )
    return stream.getvalue()


class ContextualRagTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryLibrary()
        self.source = register_sample(
            self.repo, tiny_docx(), 'original.docx',
            title='Reviewed sample 1',
            contract_types=['trade_commission'], language='en',
        )

    def test_private_source_index_has_sha_and_does_not_publish_raw_text(self):
        result = index_private_original(self.repo, self.source['id'])
        self.assertEqual(result['status'], 'indexed')
        row = self.repo.get_library_record(self.source['id'])
        index = private_index(row)
        self.assertEqual(index['sha256'], row['content_hash'])
        self.assertEqual(index['sections'][0]['text'],
                         'PRIVATE Original Company and negotiated terms')
        self.assertFalse(read_manifest(row).approved)
        hits = search_library_topics(
            self.repo, {'contract_type': 'trade_commission'},
            [{'key': 'scope', 'query': 'Company private scope'}], env={},
        )
        self.assertFalse(hits['references'])
        self.assertNotIn('PRIVATE', json.dumps(hits))
        self.assertEqual(index_private_original(self.repo, self.source['id'])['status'],
                         'already_indexed')

    def test_tampered_original_fails_closed_without_database_changes(self):
        self.repo.files[self.source['storage_path']] = b'not the original'
        before = deepcopy(self.repo.rows[self.source['id']])
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            index_private_original(self.repo, self.source['id'])
        self.assertEqual(self.repo.rows[self.source['id']], before)

    def test_explicit_approval_and_deidentification_required(self):
        index_private_original(self.repo, self.source['id'])
        before = deepcopy(self.repo.rows[self.source['id']])
        section = private_index(before)['sections'][0]
        example = {'section_id': section['id'], 'topic': 'commission payment',
                   'text': 'Payment conditions shall be agreed in writing after '
                           'the parties review the funding receipt evidence.'}
        with self.assertRaises(PermissionError):
            approve_source_excerpts(self.repo, self.source['id'], [example])
        self.assertEqual(self.repo.rows[self.source['id']], before)
        with self.assertRaisesRegex(ValueError, '제거'):
            approve_source_excerpts(
                self.repo, self.source['id'],
                [dict(example, text='Commission is 3% and payment is due after funding.')],
                explicit_approval=True)
        self.assertEqual(self.repo.rows[self.source['id']], before)
        result = approve_source_excerpts(
            self.repo, self.source['id'], [example], explicit_approval=True,
            env={}, embedder=lambda texts, **kwargs: [[1.0] + [0.0]*511 for _ in texts],
        )
        self.assertEqual(result['chunks_added'], 1)
        self.assertEqual(result['embedded'], 1)
        self.assertEqual(approve_source_excerpts(
            self.repo, self.source['id'], [example], explicit_approval=True)['chunks_added'], 0)
        row = self.repo.get_library_record(self.source['id'])
        self.assertEqual(row['extraction_status'], 'library_approved')
        approved = read_manifest(row).chunks[0]
        self.assertEqual(approved.source_section_id, section['id'])
        self.assertNotIn('PRIVATE', approved.text)
        self.assertEqual(len(approved.embedding), 512)
        hits = search_library_topics(
            self.repo, {'contract_type': 'trade_commission'},
            [{'key': 'payment', 'query': 'payment conditions funding receipt'}],
            env={}, embedder=lambda texts, **kwargs: [[1.0] + [0.0]*511 for _ in texts],
        )
        self.assertTrue(hits['sources'])
        self.assertEqual(hits['sources'][0]['source_section_id'], section['id'])
        self.assertEqual(hits['sources'][0]['matched_topics'], ['payment'])
        self.assertNotIn('PRIVATE', json.dumps(hits))

    def test_parent_context_comes_only_from_approved_neighbor_chunks(self):
        doc = make_docx([
            'Article 1 Scope. Parties shall define the specific introduction and cooperation scope.',
            'Article 2 Payment. The parties shall agree a clear fee trigger based on evidence.',
            'Article 3 Termination. Accrued obligations remain after the contractual termination.',
        ])
        row = register_sample(self.repo, doc, 'three_sections.docx',
                              title='Private structured contract',
                              contract_types=['trade_commission'], language='en')
        indexed = index_private_original(self.repo, row['id'])
        self.assertEqual(indexed['sections'], 3)
        sec = private_index(self.repo.get_library_record(row['id']))['sections']
        text_for = lambda x: (
            'The reviewer confirms the current contract must preserve '
            'clarity about ' + x + ' without inheriting historic business facts.'
        )
        first = {'section_id': sec[0]['id'], 'topic': 'scope',
                 'text': text_for('scope')}
        middle = {'section_id': sec[1]['id'], 'topic': 'payment',
                  'text': text_for('payment')}
        last = {'section_id': sec[2]['id'], 'topic': 'termination',
                'text': text_for('termination')}
        approve_source_excerpts(
            self.repo, row['id'], [middle], explicit_approval=True,
        )
        self.assertEqual(approved_neighbor_context(
            self.repo.get_library_record(row['id']), sec[1]['id']), [])
        approve_source_excerpts(
            self.repo, row['id'], [first, last], explicit_approval=True,
        )
        neighbors = approved_neighbor_context(
            self.repo.get_library_record(row['id']), sec[1]['id'])
        self.assertEqual({n['relation'] for n in neighbors}, {'before', 'after'})
        self.assertNotIn('Article 2', json.dumps(neighbors))

    def test_cross_document_comparison_validates_ids_and_excludes_private_text(self):
        index_private_original(self.repo, self.source['id'])
        doc = make_docx([
            'Article 1 Payment. The introduction remuneration duty shall be '
            'defined against receipt of agreed documentation.',
        ])
        second = register_sample(self.repo, doc, 'second.docx',
                                 title='Reviewed sample 2',
                                 contract_types=['trade_commission'], language='en')
        index_private_original(self.repo, second['id'])
        for row in [self.source, second]:
            sec = private_index(self.repo.get_library_record(row['id']))['sections'][0]
            approve_source_excerpts(
                self.repo, row['id'],
                [{'section_id': sec['id'], 'topic': 'commission payment',
                  'text': 'The fee trigger must clearly identify the recipient '
                          'and supporting evidence for commission settlement.'}],
                explicit_approval=True,
            )
        topics = [{'key': 'payment', 'query': 'commission payment settlement evidence'}]
        hits = search_library_topics(
            self.repo, {'contract_type': 'trade_commission'},
            topics, env={},
        )
        plan = {'topics': topics}
        options = build_comparison_candidates(
            self.repo.list_library_records(approved_only=True), hits['sources'], plan)
        self.assertEqual(len(options), 1)
        self.assertEqual(len(options[0]['candidates']), 2)
        first = options[0]['candidates'][0]['reference_id']

        with patch('Quotation_KEKOREA.contracts.service._call',
                   return_value={'decisions': [
                       {'topic_key': 'payment', 'selected_id': first,
                        'reason': 'Closer to confirmed payment trigger and evidence.',
                        'conflicts': ['Confirm the payment deadline.']}
                   ]}) as mocked:
            result = compare_approved_clauses(
                {'contract_type': 'trade_commission', 'terms': []},
                options, env={'OPENAI_API_KEY': 'fake', 'OPENAI_MODEL': 'fake'})
        self.assertEqual(result['status'], 'compared')
        self.assertEqual(result['decisions'][0]['selected_id'], first)
        self.assertEqual(len(result['decisions'][0]['alternatives']), 1)
        self.assertNotIn('PRIVATE', json.dumps(mocked.call_args.kwargs))
        self.assertNotIn('PRIVATE', json.dumps(mocked.call_args.args))

        with patch('Quotation_KEKOREA.contracts.service._call',
                   return_value={'decisions': [
                       {'topic_key': 'payment', 'selected_id': 'invented',
                        'reason': 'Made up selection', 'conflicts': []},
                   ]}):
            fallback = compare_approved_clauses(
                {'contract_type': 'trade_commission', 'terms': []},
                options, env={'OPENAI_API_KEY': 'fake', 'OPENAI_MODEL': 'fake'})
        self.assertEqual(fallback['status'], 'fallback')
        self.assertEqual(fallback['decisions'], [])


if __name__ == '__main__':
    unittest.main()
