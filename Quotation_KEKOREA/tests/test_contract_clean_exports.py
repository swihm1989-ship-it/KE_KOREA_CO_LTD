"""Tests for contract-only drafts and explicitly authorized final output."""
import base64
import io
import unittest
from zipfile import ZipFile

from docx import Document
from Quotation_KEKOREA.contracts.draft_exports import export_draft
from Quotation_KEKOREA.contracts.exports import export_contract
from Quotation_KEKOREA.contracts.final_policy import final_document_blockers


# Test-only PNG, not the real company seal.
TEST_STAMP = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAFklEQVR4nGP8z8DwnwEPYMInOXwUAAASWwIOH0pJXQAAAABJRU5ErkJggg==')


def sample(text='월 인도 일정은 서면 합의로 결정한다.'):
    return {
        'contract_id':'test','revision':1,'contract_type':'sale','language':'ko',
        'title':'공급 계약서',
        'clauses':[{'id':'c1','order':1,'title':'인도 및 일정',
                    'sentences':[{'id':'s1','text':text,'term_ids':[],'source_refs':[]}]}],
        'terms':[], 'issues':[],
        'parties':[{'legal_name':'KE KOREA CO. LTD','roles':['seller']},
                   {'legal_name':'OCI Co. Ltd.','roles':['buyer']}],
    }


class CleanContractExportTests(unittest.TestCase):
    def test_draft_contains_only_authored_terms_no_audit_appendix(self):
        data=export_draft(sample(),formats=('docx',))['docx']['content']
        doc=Document(io.BytesIO(data))
        body='\n'.join(p.text for p in doc.paragraphs)
        self.assertIn('월 인도 일정은 서면 합의로 결정한다.',body)
        self.assertNotIn('미확정 사항 부록',body)
        self.assertNotIn('[미확정 원문]',body)
        self.assertNotIn('[확인 필요]',body)

    def test_final_can_be_prepared_with_missing_structured_details(self):
        self.assertEqual(final_document_blockers(sample()),[])

    def test_final_blocks_authored_placeholder_without_silently_deleting(self):
        errors=final_document_blockers(sample('월 인도일은 [서명 전 확인]으로 한다.'))
        self.assertTrue(errors)
        colon = final_document_blockers(sample('[서명 전 확인: 배상 한도는 양 당사자가 서면 합의한다.]'))
        self.assertTrue(colon)
        self.assertEqual(final_document_blockers(
            sample('[서명 전 확인: 배상 한도는 양 당사자가 서면 합의한다.]'),
            allow_unresolved_text=True), [])

    def test_user_may_explicitly_export_unresolved_authored_text(self):
        original = sample('배상 한도는 [서명 전 확인]으로 한다.')
        self.assertTrue(final_document_blockers(original))
        self.assertEqual(final_document_blockers(original, allow_unresolved_text=True), [])
        # The opt-in never silently deletes or resolves the authored wording.
        docx = export_contract(original, formats=('docx',))['docx']['content']
        body = '\\n'.join(p.text for p in Document(io.BytesIO(docx)).paragraphs)
        self.assertIn('[서명 전 확인]', body)

    def test_opt_in_does_not_bypass_signatories_or_reconciliation(self):
        original = sample('손해배상 한도는 [서명 전 확인]으로 한다.')
        original['parties'] = [{'legal_name': 'Unknown', 'roles': ['seller']}]
        original['pending_reconciliation'] = {'changes': ['pending']}
        problems = final_document_blockers(original, allow_unresolved_text=True)
        self.assertTrue(any('본문 반영' in msg for msg in problems))
        self.assertTrue(any('KE KOREA' in msg for msg in problems))
        self.assertTrue(any('매도인·매수인' in msg for msg in problems))

    def test_final_docx_places_only_one_stamp_on_ke_korea_party(self):
        result=export_contract(sample(),formats=('docx',),seal_bytes=TEST_STAMP)
        data=result['docx']['content']
        with ZipFile(io.BytesIO(data)) as z:
            pictures=[name for name in z.namelist() if name.startswith('word/media/')]
        self.assertEqual(len(pictures),1)

    def test_final_pdf_still_renders(self):
        data=export_contract(sample(),formats=('pdf',),seal_bytes=TEST_STAMP)['pdf']['content']
        self.assertTrue(data.startswith(b'%PDF-'))


if __name__=='__main__':
    unittest.main()
