"""Transactional install of branded authentication + resilient BOX3 revision UI."""
import ast
from datetime import datetime
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path.cwd()
PACKAGE = Path(__file__).resolve().parent
APP = Path('Quotation_KEKOREA/app.py')
SERVICE = Path('Quotation_KEKOREA/contracts/service.py')
WORKSPACE = Path('Quotation_KEKOREA/contracts/workspace.py')
UI = Path('Quotation_KEKOREA/contracts/ui.py')
REQ = Path('Quotation_KEKOREA/requirements.txt')
AUTH = [Path('Auth/__init__.py'),Path('Auth/session.py'),Path('Auth/gate.py')]
TEST = Path('Quotation_KEKOREA/tests/test_auth_session.py')
REVIEW_TEST = Path('Quotation_KEKOREA/tests/test_contract_issue_normalization_secure.py')
THREE_BOX_TEST = Path('Quotation_KEKOREA/tests/test_contract_three_box_ui.py')
READMES = [Path(x) for x in ('README.md','Quotation_KEKOREA/README.md',
 'Quotation_KEKOREA/README_CONTRACTS.md','Quotation_KEKOREA/Team/README.md','Quotation_KEKOREA/Presentation/README.md')]
ORIGINAL = [APP,SERVICE,WORKSPACE,UI,REQ,*READMES]
for path in ORIGINAL:
    if not (ROOT/path).is_file():
        raise SystemExit(f'필수 프로젝트 파일 없음: {path}. KE_KOREA_CO_LTD 루트 폴더에서 실행하세요.')


def replace_once(text, old, new, what):
    if new in text: return text
    if text.count(old) != 1:
        raise RuntimeError(f'{what}: 예상 코드를 정확히 찾지 못했습니다. 사용자 원본을 변경하지 않습니다. found={text.count(old)}')
    return text.replace(old, new, 1)


def replace_function(source, name, transform):
    parsed=ast.parse(source)
    found=[n for n in parsed.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    if len(found)!=1:raise RuntimeError(f'{name}: 함수 검색 실패 ({len(found)}건). 원본 유지')
    node=found[0]
    lines=source.splitlines(keepends=True)
    block=''.join(lines[node.lineno-1:node.end_lineno])
    changed=transform(block)
    after=''.join(lines[:node.lineno-1])+changed+''.join(lines[node.end_lineno:])
    ast.parse(after)
    return after


def update(files):
    app=files[APP]
    anchor='with st.sidebar:\n    logo = ROOT / "assets" / "company_logo.png"'
    if 'require_login(ROOT)' not in app:
        app=replace_once(app,anchor,
            'from Auth.gate import require_login\nrequire_login(ROOT)\n\n\n'+anchor,
            '앱 진입 인증 게이트')
    files[APP]=app

    req=files[REQ]
    if not any(line.startswith('streamlit-cookies-manager') for line in req.splitlines()):
        req=req.rstrip()+'\nstreamlit-cookies-manager>=0.2,<1\n'
    files[REQ]=req

    def repair_normalizer(block):
        begin=block.index('    normalized = []')
        prefix=block[:begin]
        # Retain fail-closed behavior for non-list; allow legible string issues,
        # and preserve all original issue metadata.
        body='''    normalized = []
    for issue in issues:
        if isinstance(issue, str):
            if not issue.strip():
                raise ValueError('AI 검토사항이 비어 있습니다. 기존 계약과 메모는 유지됩니다.')
            candidate = {'code': 'ai_review_text', 'severity': 'confirm', 'message': issue.strip()}
        elif isinstance(issue, dict):
            candidate = dict(issue)
        else:
            raise ValueError('AI 검토사항의 자료 형식이 올바르지 않습니다. 기존 계약과 메모는 유지됩니다.')
        message = candidate.get('message')
        if not isinstance(message, str) or not message.strip():
            raise ValueError('AI 검토사항 문구가 누락됐습니다. 기존 계약과 메모는 유지됩니다.')
        candidate['message'] = message.strip()
        if candidate.get('severity') not in {'block', 'confirm', 'info'}:
            reported = candidate.get('severity')
            candidate['severity'] = 'confirm'
            candidate['message'] += (' (AI 분류가 명확하지 않아 사용자 확인 필요: '
                                     + str(reported)[:40] + ')')
        if not isinstance(candidate.get('code'), str) or not candidate['code'].strip():
            candidate['code'] = 'ai_review'
        normalized.append(candidate)
    return normalized
'''
        if '    normalized = []' not in block:
            raise RuntimeError('AI 검토사항 정규화 함수 구조가 예상과 다릅니다.')
        return prefix+body
    files[SERVICE]=replace_function(files[SERVICE], '_normalize_ai_issues', repair_normalizer)

    def update_workspace(block):
        """Enhance the AI prompt in-place independent of quote/line-break style.

        This is only advisory: the defensive issue normalizer is mandatory,
        whereas prompt wording must never prevent installing the auth gate.
        """
        if 'Use [] when there are no issues;' in block:
            return block
        phrase = 'report uncertainty as an issue.'
        if block.count(phrase) == 1:
            extra = (' Return issues as a list of objects with code, severity '
                     '(block/confirm/info), and nonempty message. '
                     'Use [] when there are no issues; never return null for issues.')
            return block.replace(phrase, phrase + extra, 1)
        # A previously customized user prompt is valid; leave it untouched.
        # All runtime issue handling is guarded by _normalize_ai_issues.
        print('알림: 커스텀 AI 프롬프트는 그대로 유지했습니다 (필수 인증/오류 복구 적용은 계속).')
        return block
    files[WORKSPACE]=replace_function(files[WORKSPACE], 'propose_notes_revision', update_workspace)

    ui=files[UI]
    if 'def _ke_render_full_revision_preview(' not in ui:
        insert='''def _ke_render_full_revision_preview(snapshot, heading):
    """Display full contractual text only, not private AI reviews or unsaved advice."""
    st.markdown(f'#### {heading}')
    st.caption(f"Revision {snapshot.get('revision')} · {'한국어' if snapshot.get('language') == 'ko' else 'English'}")
    st.markdown('**' + str(snapshot.get('title') or 'Contract') + '**')
    for clause in sorted(snapshot.get('clauses') or [], key=lambda c: c.get('order') or 0):
        st.markdown('**' + str(clause.get('title') or '') + '**')
        for sentence in clause.get('sentences') or []:
            if str(sentence.get('text') or '').strip():
                st.write(sentence['text'])
    remaining = final_document_blockers(snapshot)
    if remaining:
        st.caption(f'FINAL 생성 전 아직 확인할 본문 조건: {len(remaining)}건')
    else:
        st.caption('본문 임시 확인 문구는 없습니다. FINAL 출력은 별도 승인·검증 후 가능합니다.')


'''
        ui=replace_once(ui,'def _proposal_panel(repo, snapshot, proposal, state_key):',
            insert+'def _proposal_panel(repo, snapshot, proposal, state_key):','전체 미리보기 헬퍼')

    def update_proposal(block):
        if 'ke_pre_approval_preview' not in block:
            anchor='    batch_reviewed = True\n'
            insert='''    try:
        preview = apply_proposal(snapshot, proposal, [change['id'] for change in proposal.get('changes', [])])
    except (ValueError, RevisionConflict) as preview_error:
        st.error('수정안 전체 계약서 미리보기 실패: ' + str(preview_error))
    else:
        with st.expander('수정 전후 승인 전 전체 계약서 미리보기', expanded=True):
            _ke_render_full_revision_preview(preview, '변경 적용 예상 본문 — 아직 저장되지 않음')
    # ke_pre_approval_preview
'''
            block=replace_once(block,anchor,insert+anchor,'수정 전후 미리보기')
        marker='st.session_state[f"ke_approved_revision_preview_{snapshot[\'contract_id\']}"] = saved[\'revision\']'
        if marker not in block:
            anchor='            st.session_state[state_key] = saved\n'
            block=replace_once(block,anchor,anchor+'            '+marker+'\n','승인 후 미리보기 상태')
        return block
    ui=replace_function(ui,'_proposal_panel',update_proposal)

    if '# ke_note_issue_recovery' not in ui:
        old='''        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))


def _review_panel'''
        new='''        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))
            st.info('수정 메모는 유지됐습니다. AI 검토사항 형식을 다시 확인하거나 재요청해 주세요. 기존 계약 revision은 변경하지 않았습니다.')
            # ke_note_issue_recovery


def _review_panel'''
        ui=replace_once(ui,old,new,'메모 실패 처리 안내')
    if 'ke_approved_revision_preview' not in ui.split('def render_contract_page(',1)[1]:
        old='''            _export_panel(repo, snapshot, env)

    with st.expander("저장·복사·언어 버전 관리", expanded=False):'''
        new='''            preview_key = f"ke_approved_revision_preview_{active_id}"
            if st.session_state.get(preview_key) == snapshot['revision']:
                with st.expander('승인 후 최신 계약서 전체 미리보기', expanded=True):
                    _ke_render_full_revision_preview(snapshot, '승인된 최신 계약 본문')
            _export_panel(repo, snapshot, env)

    with st.expander("저장·복사·언어 버전 관리", expanded=False):'''
        ui=replace_once(ui,old,new,'승인 후 최신 계약서 미리보기')
    # Remove redundant seal password prompt ONLY when authenticated, retain fail-closed seal check.
    # App login is required on all pages before any DB access.
    if 'ke_authenticated_seal_gate' not in ui:
        old='''        password = st.text_input('FINAL 회사 직인 사용 암호', type='password',
                                 key=f"contract_final_seal_access_{snapshot['contract_id']}_{snapshot['revision']}")
        configured = str(env.get('CONTRACT_FINAL_SEAL_PASSWORD') or '')
        authorized = bool(configured) and hmac.compare_digest(str(password), configured)
        if not configured:
            st.caption('관리자: 비공개 Streamlit Secrets에 CONTRACT_FINAL_SEAL_PASSWORD를 설정하세요.')'''
        new='''        # ke_authenticated_seal_gate: gate.py requires an encrypted, signed login cookie.
        authorized = bool(st.session_state.get('kekorea_auth_verified', False))
        if not authorized:
            st.caption('FINAL 파일은 KE KOREA 관리자 로그인 후 생성할 수 있습니다.')'''
        # Do not modify if user has different explicit seal protection already.
        ui=replace_once(ui,old,new,'FINAL 암호 대신 로그인 권한')
    files[UI]=ui

    if THREE_BOX_TEST in files:
        t=files[THREE_BOX_TEST]
        old="        self.at.text_input(key='contract_final_seal_access_sample_1').set_value('test-password')"
        new="        self.at.session_state['kekorea_auth_verified'] = True"
        if old in t:
            t=replace_once(t, old, new, 'FINAL test login authorization')
        files[THREE_BOX_TEST]=t

    for p in READMES:
        content=files[p]
        heading='## KE KOREA authentication and BOX3 revision recovery (2026-11-09)'
        if heading not in content:
            content += ('\n\n'+heading+'\n\n'
             '- App entry is protected by `Auth/gate.py` before any contract, PDF, or Supabase UI is displayed. The login screen reuses the KE KOREA navy/blue/white theme and existing company logo.\n'
             '- Credentials come only from Streamlit server Secrets: `KEKOREA_AUTH_USERNAME`, `KEKOREA_AUTH_PASSWORD`, and a private random `KEKOREA_AUTH_SESSION_SECRET` (32+ characters). There are no committed plaintext credentials.\n'
             '- An encrypted browser cookie contains a separately HMAC-signed fixed-expiry token. Refreshes do not log out; sessions expire 12 hours after login without sliding renewal. Explicit logout clears browser credentials.\n'
             '- An authenticated session replaces the repeated FINAL seal-password prompt, but final-document blockers, explicit revision approval, and verified company-seal SHA256 checks remain required. Do not deploy with example credentials beyond a closed test.\n'
             '- BOX 3 AI note revision normalizes readable AI review strings, fails closed for malformed content, and preserves notes and existing revision on AI errors. Proposed sentence changes are compared and previewed before approval; after approval the saved contract text is shown.\n')
        files[p]=content

    files[AUTH[0]]=(PACKAGE/'Auth/__init__.py').read_text(encoding='utf-8')
    files[AUTH[1]]=(PACKAGE/'Auth/session.py').read_text(encoding='utf-8')
    files[AUTH[2]]=(PACKAGE/'Auth/gate.py').read_text(encoding='utf-8')
    files[TEST]=(PACKAGE/'tests/test_auth_session.py').read_text(encoding='utf-8')
    files[REVIEW_TEST]='''"""Regression for AI review issue normalization (never lose actionable notes)."""
import unittest
from Quotation_KEKOREA.contracts.service import _normalize_ai_issues

class IssueNormalizationTests(unittest.TestCase):
    def test_string_issue_preserved_and_flagged(self):
        issues = _normalize_ai_issues(['주소를 확인해 주세요'], 'bad')
        self.assertEqual(issues[0]['message'], '주소를 확인해 주세요')
        self.assertEqual(issues[0]['severity'], 'confirm')
    def test_existing_dict_metadata_is_preserved(self):
        issue={'id':'i1','code':'seller','message':'검토 필요','severity':'block'}
        self.assertEqual(_normalize_ai_issues([issue], 'bad')[0], issue)
    def test_unreadable_issues_fail_closed(self):
        for issues in ([None], [123], [''], [{'severity':'info'}]):
            with self.subTest(issues=issues), self.assertRaises(ValueError):
                _normalize_ai_issues(issues, 'bad')
'''


try:
    changed={p:(ROOT/p).read_text(encoding='utf-8-sig') for p in ORIGINAL}
    if (ROOT/THREE_BOX_TEST).is_file():
        changed[THREE_BOX_TEST]=(ROOT/THREE_BOX_TEST).read_text(encoding='utf-8-sig')
    update(changed)
    for p, content in changed.items():
        if p.suffix=='.py':ast.parse(content,filename=str(p))
    with tempfile.TemporaryDirectory(prefix='kekorea_auth_verify_') as td:
        temp=Path(td)
        for p,content in changed.items():
            dest=temp/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(content,encoding='utf-8')
        for p in (AUTH[1],TEST):
            dest=temp/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(changed[p],encoding='utf-8')
        import subprocess, os
        env=os.environ.copy();env['PYTHONPATH']=str(temp)
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(temp/'Quotation_KEKOREA/tests'),'-p','test_auth_session.py','-q'],
                cwd=temp,env=env,text=True,capture_output=True,timeout=20)
        if result.returncode:
            raise RuntimeError('Auth unit tests failed: '+result.stdout+result.stderr)
    updates={p:v for p,v in changed.items() if not (ROOT/p).exists() or (ROOT/p).read_text(encoding='utf-8-sig')!=v}
    if not updates:
        print('이미 설치된 내용과 동일합니다. 변경 없음.')
        sys.exit(0)
    backup=ROOT/'local_patch_backups'/('auth_revision_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    for p in updates:
        if (ROOT/p).exists():
            dest=backup/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/p,dest)
    installed=[]
    try:
        for p,v in updates.items():
            dest=ROOT/p;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(v,encoding='utf-8');installed.append(p)
    except Exception:
        for p in installed:
            bak=backup/p
            if bak.exists():shutil.copy2(bak,ROOT/p)
            else:(ROOT/p).unlink(missing_ok=True)
        raise
    print('설치 성공. 변경 파일:',len(updates))
    for p in updates:print(' -',p)
    print('백업:',backup)
    print('Streamlit Cloud Secrets 설정 및 GitHub main 푸시는 별도 단계입니다.')
except Exception as exc:
    sys.exit('수정 검증 실패. 사용자 프로젝트 코드는 변경되지 않았습니다.\n'+str(exc))
