"""Apply focused AI issue normalization and revision-preview UX without replacing unrelated code."""
from pathlib import Path
from datetime import datetime
import ast
import shutil
import tempfile
import subprocess
import sys

ROOT=Path.cwd()
SVC=Path('Quotation_KEKOREA/contracts/service.py')
WORK=Path('Quotation_KEKOREA/contracts/workspace.py')
UI=Path('Quotation_KEKOREA/contracts/ui.py')
TEST=Path('Quotation_KEKOREA/tests/test_contract_issue_preview_recovery.py')
READMES=[Path(s) for s in ('README.md','Quotation_KEKOREA/README.md','Quotation_KEKOREA/README_CONTRACTS.md','Quotation_KEKOREA/Team/README.md','Quotation_KEKOREA/Presentation/README.md')]
for p in [SVC, WORK, UI, *READMES]:
    if not (ROOT/p).is_file():
        sys.exit(f'필수 파일 없음: {p}. KE_KOREA_CO_LTD 프로젝트 최상위 폴더에서 실행하세요.')

def patch_func(source, function_name, transformer):
    tree=ast.parse(source)
    candidates=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==function_name]
    if len(candidates)!=1:
        raise RuntimeError(f'{function_name}: 함수가 하나 존재해야 합니다 (found {len(candidates)})')
    node=candidates[0]
    lines=source.splitlines(keepends=True)
    block=''.join(lines[node.lineno-1:node.end_lineno])
    changed=transformer(block)
    if changed==block:
        return source
    new=''.join(lines[:node.lineno-1])+changed+''.join(lines[node.end_lineno:])
    ast.parse(new)
    return new

def transform_normalizer(block):
    if 'if isinstance(issue, str):' in block and 'ai_review_text' in block:
        return block
    old=('''        if not isinstance(issue, dict):\n            raise ValueError("Contract AI returned an invalid review issue.")\n        candidate = dict(issue)''')
    new=('''        if isinstance(issue, str):\n            if not issue.strip():\n                raise ValueError("AI 검토사항 내용이 비어 있습니다. 계약과 메모는 변경하지 않았습니다.")\n            candidate = {"code": "ai_review_text", "severity": "confirm",\n                         "message": issue.strip()}\n        elif isinstance(issue, dict):\n            candidate = dict(issue)\n        else:\n            raise ValueError("AI 검토사항에 해석할 수 없는 데이터가 포함됐습니다. 계약과 메모는 변경하지 않았습니다.")''')
    if block.count(old)!=1:
        raise RuntimeError('service.py AI 검토사항 검증 코드가 예상과 다릅니다. 원본은 변경하지 않습니다.')
    return block.replace(old,new)

def transform_workspace(block):
    marker="'Return issues as an array of objects with nonempty message, code, and severity (block/confirm/info). '"
    if marker in block:
        return block
    old="'Do not return term_key changes or modify protected payment clauses; report uncertainty as an issue.',"
    new=("'Do not return term_key changes or modify protected payment clauses; report uncertainty as an issue. '\n"
         "        'Return issues as an array of objects with nonempty message, code, and severity (block/confirm/info). '\n"
         "        'Use [] when there are no issues; never put free-form strings into issues.',")
    if block.count(old)!=1:
        raise RuntimeError('workspace.py 메모 AI 호출 코드가 예상과 다릅니다. 원본은 변경하지 않습니다.')
    return block.replace(old,new,1)

PREVIEW_FUNC='''def _render_revision_preview(snapshot, heading):
    """Display the complete saved or proposed clause text, never implicitly approve it."""
    st.markdown(f'#### {heading}')
    st.caption(f"Revision {snapshot.get('revision')} · {'한국어' if snapshot.get('language') == 'ko' else 'English'} · 실제 문서 본문 미리보기")
    st.markdown(f"**{snapshot.get('title') or 'Contract'}**")
    for clause in sorted(snapshot.get('clauses') or [], key=lambda c: int(c.get('order') or 0)):
        st.markdown(f"**{clause.get('title') or ''}**")
        for sentence in clause.get('sentences') or []:
            if str(sentence.get('text') or '').strip():
                st.write(sentence['text'])
    blockers = final_document_blockers(snapshot)
    if blockers:
        st.caption(f'최종 PDF 생성 전 해결할 실제 본문 조건 {len(blockers)}건. 미리보기와 최종 날인은 별개의 단계입니다.')
    else:
        st.caption('본문 차단 조건은 발견되지 않았습니다. FINAL 생성 시 승인 및 회사 직인 권한을 별도 확인합니다.')

'''

def transform_proposal(block):
    if '최종 수정안 전체 계약서 미리보기' in block:
        return block
    anchor='''    batch_reviewed = True
'''
    insert='''    # Show the entire candidate contract before the user approves the revision.
    # Dry-run uses the unchanged revision engine and makes no persistence calls.
    try:
        preview = apply_proposal(snapshot, proposal, [c['id'] for c in proposal.get('changes', [])])
    except (ValueError, RevisionConflict) as exc:
        st.error('수정안 전체 미리보기를 만들 수 없습니다: ' + str(exc))
    else:
        with st.expander('최종 수정안 전체 계약서 미리보기', expanded=True):
            _render_revision_preview(preview, '변경 적용 전 미리보기 — 아직 승인되지 않음')
'''
    if block.count(anchor)!=1:
        raise RuntimeError('ui.py 비교/승인 패널 구조가 예상과 다릅니다.')
    block=block.replace(anchor,insert+anchor,1)
    old='''            st.session_state[state_key] = saved
            st.session_state.pop("contract_pending_proposal", None)'''
    new='''            st.session_state[state_key] = saved
            st.session_state[f"contract_approved_preview_{snapshot['contract_id']}"] = saved['revision']
            st.session_state.pop("contract_pending_proposal", None)'''
    if block.count(old)!=1:
        raise RuntimeError('ui.py 수정안 승인 저장 코드를 찾을 수 없습니다.')
    return block.replace(old,new,1)

def transform_render(block):
    if "contract_approved_preview_{active_id}" in block:
        return block
    old='''            _export_panel(repo, snapshot, env)'''
    new='''            # Following an approved commit, show the saved full contract immediately.
            if st.session_state.get(f"contract_approved_preview_{active_id}") == snapshot['revision']:
                with st.expander('최종 수정 완료 — 전체 계약서 미리보기', expanded=True):
                    _render_revision_preview(snapshot, '승인·저장된 계약서')
            _export_panel(repo, snapshot, env)'''
    if block.count(old)!=1:
        raise RuntimeError('ui.py 문서 다운로드 위치가 예상과 다릅니다.')
    return block.replace(old,new,1)

def transform_batch(block):
    if "수정안 준비가 중단됐습니다." in block:
        return block
    old='''        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))'''
    # only the batch-function block, not the entire source
    new='''        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))
            st.info('수정안 준비가 중단됐습니다. 기존 계약서와 저장된 메모는 유지됩니다. 수정 내용을 다시 입력할 필요 없이 재요청할 수 있습니다.')'''
    if block.count(old)!=1:
        raise RuntimeError('ui.py 최종 수정 요청 예외 처리 위치가 예상과 다릅니다.')
    return block.replace(old,new,1)

source={(p):(ROOT/p).read_text(encoding='utf-8-sig') for p in (SVC, WORK, UI)}
updates={}
updates[SVC]=patch_func(source[SVC], '_normalize_ai_issues', transform_normalizer)
updates[WORK]=patch_func(source[WORK], 'propose_notes_revision', transform_workspace)
u=source[UI]
u=patch_func(u,'_batch_request_panel',transform_batch)
u=patch_func(u,'_proposal_panel',transform_proposal)
u=patch_func(u,'render_contract_page',transform_render)
if 'def _render_revision_preview(' not in u:
    marker='def _proposal_panel('
    if u.count(marker)!=1:
        raise RuntimeError('ui.py 수정안 패널 위치가 예상과 다릅니다.')
    u=u.replace(marker,PREVIEW_FUNC+marker,1)
ast.parse(u)
updates[UI]=u

TEST_TEXT='''"""Safe AI review issue recovery and full revision preview regression tests."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.service import _normalize_ai_issues
from Quotation_KEKOREA.contracts.workspace import propose_notes_revision
from Quotation_KEKOREA.contracts.editing import apply_proposal


class AiReviewAndPreviewTests(TestCase):
    def setUp(self):
        self.snapshot = new_snapshot('sample','sale','ko')
        self.snapshot['revision'] = 4
        self.snapshot['clauses'] = [{'id':'c1','title':'서명','order':1,'sentences':[
            {'id':'s1','text':'서명일: [서명 전 확인]'}]}]
        self.note = {'id':'n1','contract_id':'sample','sentence_id':'s1',
                     'base_revision':4,'status':'note',
                     'instruction':'서명일을 2026년 11월 9일로 수정'}

    def test_text_and_dict_issues_are_preserved_not_silently_discarded(self):
        result = _normalize_ai_issues(['검토 필요',{'code':'date','severity':'block','message':'확인'}], 'error')
        self.assertEqual([i['severity'] for i in result], ['confirm','block'])
        self.assertEqual(result[0]['code'], 'ai_review_text')

    def test_malformed_issues_fail_closed(self):
        for value in (None, 3, [], ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _normalize_ai_issues([value], 'error')

    def test_valid_notes_make_reviewable_preview_without_automatic_commit(self):
        before=deepcopy(self.snapshot)
        def fake_call(*_args,**_kwargs):
            return {'changes':[{'id':'change1','sentence_id':'s1',
                      'original_text':'서명일: [서명 전 확인]',
                      'proposed_text':'서명일: 2026년 11월 9일',
                      'delete_sentence':False,'required_to_resolve_conflict':False}],
                    'issues':['통지처도 확인'], 'conflicts': []}
        with patch('Quotation_KEKOREA.contracts.service._call',side_effect=fake_call):
            proposal=propose_notes_revision(self.snapshot,[self.note],env={})
        self.assertEqual(self.snapshot,before)
        candidate=apply_proposal(self.snapshot, proposal, [x['id'] for x in proposal['changes']])
        self.assertEqual(candidate['revision'],5)
        self.assertEqual(candidate['clauses'][0]['sentences'][0]['text'],'서명일: 2026년 11월 9일')
        self.assertEqual(self.snapshot['revision'],4)
        self.assertEqual(self.note['status'],'note')

    def test_bad_ai_issue_keeps_contract_and_note_unchanged(self):
        before=deepcopy((self.snapshot,self.note))
        def fake_call(*_args,**_kwargs):
            return {'changes':[{'id':'change1','sentence_id':'s1',
                      'original_text':'서명일: [서명 전 확인]',
                      'proposed_text':'서명일: 2026년 11월 9일',
                      'delete_sentence':False,'required_to_resolve_conflict':False}],
                    'issues':[None], 'conflicts': []}
        with patch('Quotation_KEKOREA.contracts.service._call',side_effect=fake_call):
            with self.assertRaises(ValueError):
                propose_notes_revision(self.snapshot,[self.note],env={})
        self.assertEqual((self.snapshot,self.note), before)
'''
updates[TEST]=TEST_TEXT
NOTE='''## 2026-11-09 BOX 3 note revision preview reliability

- `contracts/service.py`: preserve nonempty free-text AI review issues as unconfirmed review items, while rejecting malformed/empty issue data without accepting or discarding risks.
- `contracts/workspace.py`: explicitly request structured AI issue objects; keep the revision and user notes unchanged until review/approval.
- `contracts/ui.py`: display entire proposed contract in the existing revision-comparison panel, and the full saved contract immediately after approval. Keep approval/commit and FINAL seal authorization separate; display a helpful message on proposal errors.
- `tests/test_contract_issue_preview_recovery.py`: cover recoverable AI issues, invalid issues, proposal preview integrity and unchanged source revision.
'''
for p in READMES:
    text=(ROOT/p).read_text(encoding='utf-8-sig')
    updates[p]=text if '## 2026-11-09 BOX 3 note revision preview reliability' in text else text.rstrip()+'\n\n'+NOTE.strip()+'\n'
for p in (SVC,WORK,UI,TEST): ast.parse(updates[p],filename=str(p))
# Fast local test in temp project by copying only module files required for tests.
with tempfile.TemporaryDirectory(prefix='ke_preview_validate_') as temp:
    stage=Path(temp)
    contracts=ROOT/'Quotation_KEKOREA/contracts'
    if (contracts/'models.py').exists():
        for p in contracts.glob('*.py'):
            dst=stage/'Quotation_KEKOREA/contracts'/p.name
            dst.parent.mkdir(parents=True,exist_ok=True)
            dst.write_bytes(p.read_bytes())
        for p in (SVC,WORK,UI):
            (stage/p).write_text(updates[p],encoding='utf-8')
        (stage/'Quotation_KEKOREA/tests').mkdir(parents=True)
        (stage/TEST).write_text(TEST_TEXT,encoding='utf-8')
        for p in (stage/'Quotation_KEKOREA/__init__.py',stage/'Quotation_KEKOREA/tests/__init__.py'):
            p.parent.mkdir(parents=True,exist_ok=True)
            p.touch()
        if (stage/'Quotation_KEKOREA/contracts/__init__.py').exists() is False:
            (stage/'Quotation_KEKOREA/contracts/__init__.py').touch()
        result=subprocess.run([sys.executable,'-m','unittest','Quotation_KEKOREA.tests.test_contract_issue_preview_recovery','-q'],cwd=stage,capture_output=True,text=True,timeout=45)
        if result.returncode:
            raise RuntimeError('임시 검증 실패. 원본 미변경:\n'+(result.stdout+result.stderr)[-2300:])
        print('새 회귀 테스트:',result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'OK')
    else:
        print('참고: models.py가 없어 AST와 구조 검증만 진행합니다. 설치 후 앱 테스트를 실행하세요.')
changed=[p for p,c in updates.items() if not (ROOT/p).is_file() or (ROOT/p).read_text(encoding='utf-8-sig')!=c]
if not changed:
    print('이미 설치된 패치입니다. 소스 변경 없음.')
    sys.exit(0)
backup=ROOT/'local_patch_backups'/('revision_preview_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
try:
    for p in changed:
        if (ROOT/p).is_file():
            dst=backup/p;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/p,dst)
    for p in changed:
        dst=ROOT/p;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(updates[p],encoding='utf-8')
except Exception:
    for p in changed:
        old=backup/p
        if old.is_file(): shutil.copy2(old,ROOT/p)
        elif (ROOT/p).is_file(): (ROOT/p).unlink()
    raise
print('설치 완료:',len(changed),'개 파일')
for p in changed: print('  ',p)
print('백업:',backup)
print('GitHub 및 Streamlit 자동 배포는 하지 않았습니다.')
