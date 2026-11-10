# Targeted compatibility patch for the existing clean exports revision.
from pathlib import Path
from datetime import datetime
from shutil import copy2
import ast
import sys
ROOT=Path.cwd(); B=ROOT/'Quotation_KEKOREA'
UI=B/'contracts/ui.py'
RULES=B/'contracts/rules.py'
TEST_BOX=B/'tests/test_contract_three_box_ui.py'
TEST_WORK=B/'tests/test_contract_workspace_actions.py'
README=[ROOT/'README.md',B/'README.md',B/'README_CONTRACTS.md',B/'Team/README.md',B/'Presentation/README.md']
paths=[UI,RULES,TEST_BOX,TEST_WORK,*README]
for p in paths:
    if not p.is_file(): sys.exit('Missing: '+str(p))
if not (B/'contracts/final_policy.py').exists():
    sys.exit('Previous clean-contract-export patch is not installed. Apply it first, then re-run this patch.')

def replace_one(text, old, new, label):
    n=text.count(old)
    if n != 1: raise RuntimeError(f'{label}: expected 1 occurrence, found {n}. No files changed.')
    return text.replace(old,new,1)

updates={}
s=UI.read_text(encoding='utf-8')
# party roles are in parties; show them once in the table below.
s=replace_one(s,'''    keys = list(dict.fromkeys(list(TYPE_REQUIRED[snapshot["contract_type"]]) +
                              list(terms.keys())))''', '''    # Buyer/Seller/commission signatories live exclusively in snapshot['parties'].
    # Do not create empty duplicate term rows for the same parties.
    party_roles = {'buyer', 'seller', 'client', 'intermediary', 'commission_payer',
                   'fundraiser', 'investor'}
    keys = [key for key in dict.fromkeys(list(TYPE_REQUIRED[snapshot["contract_type"]]) +
                                               list(terms.keys())) if key not in party_roles]''', 'remove redundant role rows')
s=replace_one(s,'''    for key in keys:
        term = terms.get(key, {})
        rows.append({''','''    for key in keys:
        term = terms.get(key, {})
        display_term = term
        # Qty may already carry the unit: 50000 KG/month. Offer KG as a suggestion
        # without upgrading its approval status or overwriting a known unit.
        if key == 'unit' and not str(term.get('value') or '').strip():
            qty_unit = str(terms.get('quantity', {}).get('unit') or '').strip().upper()
            matched = re.match(r'^(KG|MT|PCS|TON|LB)(?:\s*(?:/|PER|당))?', qty_unit)
            if matched:
                display_term = {'value': matched.group(1), 'status': 'suggested'}
        rows.append({''','unit suggestion')
s=replace_one(s,'''            "항목": LABELS.get(key, key.replace("_", " ")),
            "value": term.get("value") or "",
            "unit": term.get("unit") or "",
            "currency": term.get("currency") or "",
            "status": _editor_status(term.get("status", "missing"), term.get('value')),''','''            "항목": ('매매대금 지급 조건' if key == 'payment_trigger'
                     and snapshot['contract_type'] == 'sale' else LABELS.get(key, key.replace("_", " "))),
            "value": display_term.get("value") or "",
            "unit": term.get("unit") or "",
            "currency": term.get("currency") or "",
            "status": _editor_status(display_term.get("status", "missing"), display_term.get('value')),''','term row labels and display')
# Previous clean exports require explicit acceptance and password; ensure archived test is aligned.
updates[UI]=s
s=RULES.read_text(encoding='utf-8')
s=replace_one(s,'''    "payment_trigger": "수수료 지급 트리거 (실제 입금 대상·계좌 포함)",''', '''    # The sale UI uses a dedicated label; commission policy is in its own workflow.
    "payment_trigger": "매매대금 또는 수수료 지급 조건",''','payment label duplicate')
updates[RULES]=s
s=TEST_WORK.read_text(encoding='utf-8')
s=replace_one(s,"def test_draft_has_labels_unresolved_appendix_and_no_signature_page(self):", "def test_draft_has_only_contract_content_and_no_signature_page(self):",'draft test name')
s=replace_one(s,'''        self.assertIn('[필수 확인]', text)
        self.assertIn('미확정 사항', text)''','''        self.assertNotIn('[필수 확인]', text)
        self.assertNotIn('미확정 사항', text)
        self.assertNotIn('[미확정 원문]', text)''','no appendix DOCX')
s=replace_one(s,'''            self.assertIn('미확정 사항', ''.join(p.get_text() for p in pdf))''','''            self.assertNotIn('미확정 사항', ''.join(p.get_text() for p in pdf))''','no appendix PDF')
s=replace_one(s,'def test_english_draft_preserves_korean_original_evidence_in_pdf(self):','def test_english_draft_does_not_leak_review_evidence_in_pdf(self):','english test name')
s=replace_one(s,"        self.assertIn('계약일 또는 효력 발생 기준', text)","        self.assertNotIn('계약일 또는 효력 발생 기준', text)\n        self.assertIn('첫 번째 계약 문장입니다.', text)",'english test assertion')
updates[TEST_WORK]=s
s=TEST_BOX.read_text(encoding='utf-8')
# Existing fixture did not configure final approval/password and has no KE KOREA party.
old='''    def test_final_download_uses_existing_validation_and_renderer(self):
        from Quotation_KEKOREA.contracts.rules import COMMON_REQUIRED, TYPE_REQUIRED, validate_snapshot
        snapshot = self.repo.revisions['sample'][0]['snapshot']
        snapshot['issues'] = []
        snapshot['terms'] = [dict(key=key, value='Agreed value', status='confirmed')
                             for key in COMMON_REQUIRED + TYPE_REQUIRED['sale'] if key not in {'buyer', 'seller'}]
        snapshot['parties'] = [dict(id=role, legal_name=role + ' Example Ltd', country='KR', address='Seoul',
                                   roles=[role], status='confirmed') for role in ('buyer', 'seller')]
        self.assertEqual(validate_snapshot(snapshot, for_export=True), [])
        self.run_app()
        self.assertFalse(self.button('최종 계약서 PDF').disabled)
        self.button('최종 계약서 PDF').click()
        self.run_app()
        self.assertEqual(len(self.repo.exports), 1)
        self.assertIn('/exports/final/', self.repo.exports[0]['storage_path'])
        self.assertNotIn('-DRAFT-', self.repo.exports[0]['storage_path'])'''
new='''    def test_final_download_uses_current_revision_approval_and_verified_seal(self):
        # Old test expected an enabled button without the explicit approval,
        # administrator authorization or KE KOREA party now required for stamping.
        from Quotation_KEKOREA.contracts.rules import COMMON_REQUIRED, TYPE_REQUIRED, validate_snapshot
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        snapshot = self.repo.revisions['sample'][0]['snapshot']
        snapshot['issues'] = []
        snapshot['terms'] = [dict(key=key, value='Agreed value', status='confirmed')
                             for key in COMMON_REQUIRED + TYPE_REQUIRED['sale'] if key not in {'buyer', 'seller'}]
        snapshot['parties'] = [dict(id='seller', legal_name='KE KOREA CO. LTD', country='KR', address='Seoul',
                                   roles=['seller'], status='confirmed'),
                               dict(id='buyer', legal_name='OCI Co. Ltd.', country='KR', address='Seoul',
                                   roles=['buyer'], status='confirmed')]
        self.assertEqual(validate_snapshot(snapshot, for_export=True), [])
        self.at = AppTest.from_string(
            "from Quotation_KEKOREA.contracts.ui import render_contract_page\\n"
            "render_contract_page('계약서 만들기', {'CONTRACT_FINAL_SEAL_PASSWORD':'test-password'})")
        self.at.session_state['contract_active_id'] = 'sample'
        self.run_app()
        self.assertTrue(self.button('최종 계약서 PDF').disabled)
        self.at.checkbox(key='contract_final_approved_sample_1').check()
        self.at.text_input(key='contract_final_seal_access_sample_1').set_value('test-password')
        self.run_app()
        self.assertFalse(self.button('최종 계약서 PDF').disabled)
        # Verify workflow wiring with a synthetic renderer result, never a real seal.
        def mock_renderer(snap, *, formats, seal_bytes):
            self.assertEqual(snap['revision'], 1)
            self.assertEqual(formats, ('pdf',))
            self.assertEqual(seal_bytes, b'test-seal-bytes')
            return {'pdf': {'filename': 'test-final.pdf', 'content': b'%PDF-1.4\\n%%EOF',
                            'sha256': 'testhash', 'revision': 1}}
        with patch('Quotation_KEKOREA.contracts.ui._verified_contract_seal',
                   return_value=b'test-seal-bytes'), patch(
                   'Quotation_KEKOREA.contracts.ui.export_contract', side_effect=mock_renderer):
            self.button('최종 계약서 PDF').click()
            self.run_app()
        self.assertEqual(len(self.repo.exports), 1)
        self.assertIn('/exports/final/', self.repo.exports[0]['storage_path'])
        self.assertNotIn('-DRAFT-', self.repo.exports[0]['storage_path'])'''
s=replace_one(s,old,new,'FINAL workflow test')
# Add test for removing duplicate parties and unit derivation in UI.
anchor='''    def test_sentence_notes_reload_without_cross_contamination(self):'''
extra='''    def test_party_roles_render_only_in_parties_and_unit_is_suggested(self):
        from Quotation_KEKOREA.contracts.ui import _term_rows, _party_rows
        snapshot = self.repo.revisions['sample'][0]['snapshot']
        snapshot['terms'] = [{'key': 'quantity', 'value': '50000',
                              'unit': 'KG/월', 'status': 'confirmed'}]
        snapshot['parties'] = [{'legal_name': 'KE KOREA CO. LTD',
                                'roles': ['seller'], 'status': 'suggested'},
                               {'legal_name': 'OCI Co. Ltd.',
                                'roles': ['buyer'], 'status': 'suggested'}]
        terms = {row['key']: row for row in _term_rows(snapshot)}
        self.assertNotIn('buyer', terms)
        self.assertNotIn('seller', terms)
        self.assertEqual(terms['unit']['value'], 'KG')
        self.assertEqual(terms['unit']['status'], 'AI 제안')
        self.assertEqual(terms['payment_trigger']['항목'], '매매대금 지급 조건')
        self.assertEqual(len(_party_rows(snapshot)), 2)

'''
s=replace_one(s,anchor,extra+anchor,'new UI regression test')
updates[TEST_BOX]=s
note='''\n\n### 2026-11-09 조건표 중복 및 계약 PDF 회귀 수정 (로컬 패치·운영 미확인)\n- BOX 2 buyer/seller 등 당사자 역할을 조건표에서 중복 표시하지 않고 `parties` 표만 원본으로 사용한다. 수량 행에 KG/월 등이 명시된 경우 `unit`에 KG 후보를 보여주며 사용자 승인 전에는 확정하지 않는다. 매매계약의 `payment_trigger` 표시는 `매매대금 지급 조건`으로 바꾼다. `$`를 USD로 자동 확정하지 않는다.\n- 계약서 DRAFT PDF/DOCX의 자동 미확정 부록·검토 원문 출력은 폐지된 정책이므로 관련 회귀 테스트의 기대값을 변경한다. 내부 검토 이력은 DB/앱에 보존한다.\n- FINAL UI 테스트는 현재 revision 승인, 관리자 직인 사용 암호, KE KOREA 서명 당사자를 준비한 뒤 생성 경로를 검증한다. 실제 직인/Streamlit 배포 검증과는 별도다.\n- 기존 계약/조건표/메모/직인 원본은 수정하지 않는다. 모든 테스트를 통과하기 전에는 배포하지 않는다.\n'''
for path in README:
    text=path.read_text(encoding='utf-8')
    if '### 2026-11-09 조건표 중복 및 계약 PDF 회귀 수정' not in text:
        text += note
    updates[path]=text
# All edits validated before writes.
for p,v in updates.items():
    if p.suffix=='.py': ast.parse(v,filename=str(p))
backup=ROOT/'local_patch_backups'/('box2_pdf_regression_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
for p in updates:
    target=backup/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);copy2(p,target)
for p,v in updates.items():p.write_text(v,encoding='utf-8')
print('Updated',len(updates),'files. Backups at',backup)
print('No source data, contract records, keys, or original seals were modified.')
print('Run focused tests and all tests before commit.')
