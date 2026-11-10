"""Guarded KE KOREA contract UI repair. Run from repo root, never silently deploy."""
from pathlib import Path
from datetime import datetime
from shutil import copy2
import ast
import sys

root=Path.cwd(); base=root/'Quotation_KEKOREA'; ui=base/'contracts/ui.py'
final_policy=base/'contracts/final_policy.py'; draft=base/'contracts/draft_exports.py'; exports=base/'contracts/exports.py'
readmes=[root/'README.md', base/'README.md',base/'README_CONTRACTS.md',base/'Team/README.md',base/'Presentation/README.md']
tests=base/'tests/test_contract_three_box_ui.py'
fallback=base/'tests/test_contract_export_storage_fallback.py'
required=[ui,final_policy,draft,exports,tests,fallback,*readmes]
for p in required:
    if not p.is_file(): sys.exit('Missing file: '+str(p)+'\nPrevious clean-export patch may not have been installed.')
source=ui.read_text(encoding='utf-8')
if 'def _verified_contract_seal(' not in source or 'seal_bytes=_verified_contract_seal(env)' not in source:
    sys.exit('This patch needs the previous clean-export patch with verified seal support. No files changed.')
if '미확정 사항 부록 / TBD' in draft.read_text(encoding='utf-8'):
    sys.exit('DRAFT renderer still appends old audit appendix. Apply clean-export patch first. No files changed.')
if 'def final_document_blockers(' not in final_policy.read_text(encoding='utf-8'):
    sys.exit('Missing final_document_blockers. No files changed.')

changed={}

def func_replace(source, start, next_start, replacement):
    pos=source.find('\n'+start)
    if pos<0 and source.startswith(start): pos=-1
    if pos<0: raise ValueError('missing function: '+start)
    begin=pos+1
    end=source.find('\n'+next_start,begin)
    if end<0: raise ValueError('missing function after '+start+': '+next_start)
    return source[:begin]+replacement.rstrip()+'\n\n'+source[end+1:]

term_rows='''def _term_rows(snapshot):
    """Present canonical commercial terms; signatory roles live in parties, not terms."""
    terms = {str(t.get('key')): t for t in snapshot.get('terms', []) if t.get('key')}
    party_keys = {'buyer', 'seller', 'client', 'intermediary',
                  'commission_payer', 'fundraiser', 'investor'}
    keys = [key for key in dict.fromkeys(list(TYPE_REQUIRED[snapshot['contract_type']]) + list(terms))
            if key not in party_keys]
    if snapshot['contract_type'] in COMMISSION_TYPES:
        keys = list(dict.fromkeys(keys + ['payment_trigger', 'late_interest_legal_review',
                                         'late_interest_source']))
    rows = []
    for key in keys:
        term = terms.get(key, {})
        value = term.get('value') or ''
        status = term.get('status', 'missing')
        # Display-only candidate; persist only after a person presses the existing save button.
        if key == 'unit' and not str(value).strip():
            qty_unit = str(terms.get('quantity', {}).get('unit') or '').strip().upper()
            matched = re.match(r'^\\s*(KG|MT|PCS|TON|LB)(?:\\s*(?:/|PER|당)|$)', qty_unit)
            if matched:
                value = matched.group(1)
                status = 'suggested'
        label = ('매매대금 지급 조건' if key == 'payment_trigger' and
                 snapshot['contract_type'] == 'sale' else LABELS.get(key, key.replace('_', ' ')))
        rows.append({'key': key, '항목': label, 'value': value,
                     'unit': term.get('unit') or '', 'currency': term.get('currency') or '',
                     'status': _editor_status(status, value)})
    return rows
'''
source=func_replace(source,'def _term_rows(snapshot):','def _party_rows(snapshot):',term_rows)

# No server storage on DRAFT: direct one-click, revision-and-body-fingerprinted download.
# FINAL continues the existing authenticated seal and private storage policy.
export_panel='''def _export_panel(repo, snapshot, env):
    st.markdown('#### 문서 다운로드')
    st.caption('DRAFT와 FINAL 파일에는 BOX 3의 저장된 계약 조항만 포함됩니다. 내부 AI 검토사항은 화면에만 남습니다.')
    issues = validate_rules(snapshot, for_export=True, env=env)
    draft_col, final_col = st.columns(2)
    with draft_col:
        st.markdown('**DRAFT / 검토용**')
        st.caption('저장소 업로드 없이 한 번 클릭하여 PDF 또는 Word를 내려받습니다.')
        if any(c.get('sentences') for c in snapshot.get('clauses', [])):
            fingerprint = hashlib.sha256(repr((snapshot.get('title'), snapshot.get('language'),
                snapshot.get('revision'), snapshot.get('clauses'))).encode('utf-8')).hexdigest()
            cache_key = f"contract_direct_draft_{snapshot['contract_id']}"
            cached = st.session_state.get(cache_key)
            if not isinstance(cached, dict) or cached.get('fingerprint') != fingerprint:
                try:
                    outputs = export_draft(snapshot, formats=('pdf', 'docx'), env=env)
                except (ValueError, RuntimeError) as exc:
                    st.error(f'계약서 렌더링 실패: {exc}')
                    outputs = None
                if outputs is not None:
                    st.session_state[cache_key] = {'fingerprint': fingerprint, 'outputs': outputs}
                else:
                    st.session_state.pop(cache_key, None)
            cached = st.session_state.get(cache_key)
            if cached and cached.get('fingerprint') == fingerprint:
                for ext in ('pdf', 'docx'):
                    output = cached['outputs'][ext]
                    st.download_button(f'검토용 초안 {ext.upper()}', data=output['content'],
                                       file_name=output['filename'], mime=_contract_mime(ext),
                                       key=f"contract_direct_draft_download_{snapshot['contract_id']}_{fingerprint}_{ext}")
        else:
            st.caption('BOX 3에 실제 계약 조항을 먼저 생성하세요.')
    with final_col:
        st.markdown('**FINAL / 최종 계약서**')
        blockers = final_document_blockers(snapshot)
        if issues:
            st.caption(f'내부 검토사항 {len(issues)}건은 PDF에 출력되지 않습니다. 최종 승인 전 내용을 확인하세요.')
        for message in blockers[:6]:
            st.error(message)
        approval_key = f"contract_final_approved_{snapshot['contract_id']}_{snapshot['revision']}"
        approved = st.checkbox('현재 revision의 계약 본문 및 당사자를 확인하고 최종 파일을 승인합니다.',
                               key=approval_key)
        password = st.text_input('FINAL 회사 직인 사용 암호', type='password',
                                 key=f"contract_final_seal_access_{snapshot['contract_id']}_{snapshot['revision']}")
        configured = str(env.get('CONTRACT_FINAL_SEAL_PASSWORD') or '')
        authorized = bool(configured) and hmac.compare_digest(str(password), configured)
        if not configured:
            st.caption('관리자: 비공개 Streamlit Secrets에 CONTRACT_FINAL_SEAL_PASSWORD를 설정하세요.')
        disabled = bool(blockers) or not approved or not authorized
        for ext in ('pdf', 'docx'):
            button_key = f"contract_export_final_{snapshot['contract_id']}_{snapshot['revision']}_{ext}"
            if st.button(f'최종 계약서 {ext.upper()}', disabled=disabled, key=button_key):
                try:
                    if final_document_blockers(snapshot) or not approved or not authorized:
                        raise ValueError('현재 계약 본문 승인과 직인 사용 권한 확인이 필요합니다.')
                    outputs = export_contract(snapshot, formats=(ext,), seal_bytes=_verified_contract_seal(env))
                    local_key=f"contract_unsaved_output_final_{snapshot['contract_id']}_{snapshot['revision']}_{ext}"
                    saved_key=f"contract_output_final_{snapshot['contract_id']}_{snapshot['revision']}_{ext}"
                    # Never misreport a successful render as a successful upload.
                    try:
                        _persist_contract_outputs(repo, snapshot, outputs, 'final')
                    except ContractRepositoryError:
                        st.session_state[local_key] = outputs[ext]
                        st.session_state.pop(saved_key, None)
                        st.info('최종 파일 생성 완료. 서버 보관은 실패하여 브라우저에서 직접 다운로드할 수 있습니다.')
                    else:
                        st.session_state[saved_key] = outputs[ext]
                        st.session_state.pop(local_key, None)
                        st.success('최종 계약서 파일 생성 및 비공개 보관 완료')
                except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                    st.error(f'최종 문서 생성 실패: {exc}')
            for key, label in ((f"contract_output_final_{snapshot['contract_id']}_{snapshot['revision']}_{ext}",
                                f'최종 계약서 {ext.upper()} 다운로드'),
                               (f"contract_unsaved_output_final_{snapshot['contract_id']}_{snapshot['revision']}_{ext}",
                                f'최종 계약서 {ext.upper()} 직접 다운로드')):
                output = st.session_state.get(key)
                if output and not disabled:
                    st.download_button(label, data=output['content'], file_name=output['filename'],
                                       mime=_contract_mime(ext),
                                       key=f'contract_download_{key}')
    # Findings remain available in the app, not in exported document pages.
    _review_panel(repo, snapshot, f"contract_snapshot_{snapshot['contract_id']}", issues)
'''
source=func_replace(source,'def _export_panel(repo, snapshot, env):','def _contract_mime(extension):',export_panel)
ast.parse(source)
changed[ui]=source

# Existing test suite assumed private upload for DRAFT. Update those assumptions to
# assert no cloud storage is called. The new direct button is not an AppTest button.
s=tests.read_text(encoding='utf-8')
start=s.find('    def test_draft_private_export_allowed_while_final_stays_blocked(self):')
end=s.find('    def test_default_review_has_no_duplicated_english_error_checkbox(self):', start)
if start<0 or end<0: raise RuntimeError('Unable to locate outdated draft private export test')
s=s[:start]+'''    def test_draft_is_ready_without_storage_and_final_stays_blocked(self):
        self.run_app()
        self.assertTrue(self.button('최종 계약서 PDF').disabled)
        self.assertFalse(self.repo.exports)
        self.assertFalse(self.repo.files)
        draft = self.at.session_state['contract_direct_draft_sample']
        self.assertTrue(draft['outputs']['pdf']['content'].startswith(b'%PDF-'))
        self.assertTrue(draft['outputs']['docx']['content'].startswith(b'PK'))

'''+s[end:]
start=s.find('    def test_failed_draft_export_record_is_cleaned_up(self):')
end=s.find('\n    def ',start+8)
if start>=0:
    if end<0: end=s.find('\n\nif __name__',start)
    if end<0: end=len(s)
    s=s[:start]+'''    def test_draft_never_calls_private_storage(self):
        from Quotation_KEKOREA.contracts.repository import ContractRepositoryError
        with patch.object(self.repo, 'save_export', side_effect=ContractRepositoryError('blocked')):
            self.run_app()
        self.assertFalse(self.repo.exports)
        self.assertFalse(self.repo.files)
        self.assertTrue(self.at.session_state['contract_direct_draft_sample']['outputs']['pdf']['content'])
'''+s[end:]
ast.parse(s); changed[tests]=s

s=fallback.read_text(encoding='utf-8')
start=s.index('class ExportStorageFallbackTests(')
end=s.find("\n\nif __name__", start)
if end<0: raise RuntimeError('Cannot find fallback test footer')
s=s[:start]+'''class ExportStorageFallbackTests(ThreeBoxUiTests):
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
'''+s[end:]
ast.parse(s); changed[fallback]=s

# Focused, storage-free, deterministic direct-export regressions.
new_test=base/'tests/test_contract_flow_repair.py'
if new_test.exists():
    raise RuntimeError('test_contract_flow_repair.py already exists; no files changed')
changed[new_test]='''import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.ui import _term_rows
from Quotation_KEKOREA.contracts.final_policy import final_document_blockers


class ContractFlowRepairTests(unittest.TestCase):
    def test_roles_are_not_duplicate_term_rows(self):
        snap={'contract_type':'sale','terms':[], 'parties':[
            {'roles':['seller'],'legal_name':'KE KOREA CO. LTD'},
            {'roles':['buyer'],'legal_name':'OCI Co. Ltd.'}]}
        keys={r['key'] for r in _term_rows(snap)}
        self.assertNotIn('buyer',keys)
        self.assertNotIn('seller',keys)

    def test_user_input_unit_does_not_require_second_ai_call(self):
        snap={'contract_type':'sale','terms':[{'key':'quantity','value':'50000','unit':'KG/월','status':'confirmed'}]}
        rows={r['key']:r for r in _term_rows(snap)}
        self.assertEqual(rows['unit']['value'],'KG')
        self.assertEqual(rows['unit']['status'],'AI 제안')

    def test_existing_explicit_unit_not_overwritten(self):
        snap={'contract_type':'sale','terms':[{'key':'unit','value':'MT','status':'confirmed'},
            {'key':'quantity','value':'50','unit':'KG','status':'suggested'}]}
        rows={r['key']:r for r in _term_rows(snap)}
        self.assertEqual(rows['unit']['value'],'MT')
        self.assertEqual(rows['unit']['status'],'확정')

    def test_sale_payment_label_is_not_commission(self):
        rows={r['key']:r for r in _term_rows({'contract_type':'sale','terms':[]})}
        self.assertEqual(rows['payment_trigger']['항목'],'매매대금 지급 조건')

    def test_unverified_symbol_is_never_silently_usd(self):
        rows={r['key']:r for r in _term_rows({'contract_type':'sale','terms':[
            {'key':'currency','value':'$','status':'suggested'}]})}
        self.assertEqual(rows['currency']['value'],'$')
        self.assertEqual(rows['currency']['status'],'AI 제안')

    def test_unresolved_prose_placeholder_blocks_final(self):
        snap={'contract_type':'sale','clauses':[{'sentences':[{'text':'[서명 전 확인]'}]}],
             'parties':[{'legal_name':'KE KOREA CO. LTD','roles':['seller']},
                        {'legal_name':'OCI Co. Ltd.','roles':['buyer']}], 'pending_reconciliation':False}
        self.assertTrue(final_document_blockers(snap))
'''
ast.parse(changed[new_test]);

note='''\n\n### 2026-11-09 BOX 2·계약파일 한 번 다운로드 경로 보완 (로컬 패치, 배포 미확인)\n- Buyer/Seller 등 역할은 `parties` 표에서만 표시하고 조건표에 빈 중복 행을 생성하지 않는다. `quantity.unit`의 KG/월에서 `unit`의 KG를 미확정 후보로 제안하며 사용자 확인 없이 확정하지 않는다. 매매계약 지급조건 명칭을 수수료 지급 트리거와 구별한다. `$` 표기만으로 통화를 USD로 확정하지 않는다.\n- 검토용 DRAFT PDF/DOCX는 현재 저장된 BOX 3 제목·조항만 포함해 서버 업로드 없이 한 번 클릭으로 내려받는다. Supabase Storage 400은 DRAFT 다운로드에 영향을 미치지 않는다. revision·본문이 달라지면 다운로드 데이터를 재생성한다. 검토 이력은 화면에 보존한다.\n- FINAL은 BOX 3 현재 revision 확인, 관리자 직인 사용 인증, 명시적 본문 미확정 표시 및 당사자 검증에 따라 출력한다. BOX 2의 모든 빈칸을 억지로 채우게 강제하지 않지만, 가격·인도장소 차이 등 실제 위험은 사용자 검토를 필요로 한다. PDF 자동 날인은 비공개 SHA-256 검증 이미지만 사용한다.\n- 기존 PO/PI/CI/PL, RAG/메모/revision 기능을 변경하지 않는다. 새 직접 다운로드 흐름에 맞춰 관련 구식 업로드 테스트를 수정했다. 사용자 PC의 전체 테스트 및 운영 환경에서의 PDF 시각 검증은 별도 수행이 필요하다.\n'''
for p in readmes:
    text=p.read_text(encoding='utf-8')
    if '### 2026-11-09 BOX 2·계약파일 한 번 다운로드 경로 보완' not in text:
        text+=note
    changed[p]=text

# Abort before mutation on any Python syntax or unexpected diff anchor.
for p,text in changed.items():
    if p.suffix=='.py': ast.parse(text, filename=str(p))
backup=root/'local_patch_backups'/('contract_flow_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
for p in changed:
    if p.exists():
        b=backup/p.relative_to(root); b.parent.mkdir(parents=True,exist_ok=True); copy2(p,b)
for p,text in changed.items():
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text,encoding='utf-8')
print(f'Updated {len(changed)} files. Backup: {backup}')
print('No Git commit/push/deployment was performed. Run focused and full tests before deployment.')
