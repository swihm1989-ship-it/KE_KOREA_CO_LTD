"""Safely install narrow AI-review issue normalization fix into KE KOREA."""
from pathlib import Path
import ast
import shutil
import tempfile
from datetime import datetime

ROOT = Path.cwd()
SERVICE = Path('Quotation_KEKOREA/contracts/service.py')
WORKSPACE = Path('Quotation_KEKOREA/contracts/workspace.py')
UI = Path('Quotation_KEKOREA/contracts/ui.py')
TEST = Path('Quotation_KEKOREA/tests/test_contract_review_issue_recovery.py')
READMES = [Path('README.md'), Path('Quotation_KEKOREA/README.md'), Path('Quotation_KEKOREA/README_CONTRACTS.md'), Path('Quotation_KEKOREA/Team/README.md'), Path('Quotation_KEKOREA/Presentation/README.md')]
ALL = [SERVICE, WORKSPACE, UI, TEST, *READMES]
for p in [SERVICE, WORKSPACE, UI, *READMES]:
    if not (ROOT / p).is_file():
        raise SystemExit(f'필수 파일 없음: {p}. 프로젝트 최상위 폴더에서 실행하세요.')

NORMALIZER_OLD = '''    normalized = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("Contract AI returned an invalid review issue.")
        candidate = dict(issue)
        message = candidate.get("message")
'''
NORMALIZER_NEW = '''    normalized = []
    for issue in issues:
        if isinstance(issue, str):
            # AI occasionally returns a human-readable issue instead of an object.
            # Preserve the warning, never silently discard or mark it resolved.
            if not issue.strip():
                raise ValueError("AI 검토사항이 비어 있어 수정안을 저장하지 않았습니다. 메모는 유지됩니다.")
            candidate = {"code": "ai_review_text", "severity": "confirm",
                         "message": issue.strip()}
        elif isinstance(issue, dict):
            candidate = dict(issue)
        else:
            raise ValueError("AI 검토사항 형식이 올바르지 않습니다. 문장 메모는 유지됩니다.")
        message = candidate.get("message")
'''
UI_OLD = '''        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))


def _review_panel(repo, snapshot, state_key, issues):
'''
UI_NEW = '''        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))
            st.info('수정안 생성 또는 저장에 실패했습니다. 계약서 본문은 변경되지 않았으며, 현재 revision의 문장 메모를 유지합니다. 오류를 확인한 후 다시 요청하세요.')


def _review_panel(repo, snapshot, state_key, issues):
'''
WORKSPACE_OLD = "'Do not return term_key changes or modify protected payment clauses; report uncertainty as an issue.',"
WORKSPACE_NEW = ("'Do not return term_key changes or modify protected payment clauses; report uncertainty as an issue. '"
                 "\n        'Return issues as an array of objects with nonempty message, code, and severity (block/confirm/info). '"
                 "\n        'If no issues, return an empty array. Do not mix free-form text into issues.',")

TEST_TEXT = '''"""Regression tests for recoverable AI review issues and atomic note proposals."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from Quotation_KEKOREA.contracts.service import _normalize_ai_issues
from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.contracts.workspace import propose_notes_revision


class ReviewIssueRecoveryTests(TestCase):
    def test_string_issue_is_preserved_as_unconfirmed_review(self):
        result = _normalize_ai_issues(['서명자 확인 필요'], 'error')
        self.assertEqual(result[0]['message'], '서명자 확인 필요')
        self.assertEqual(result[0]['severity'], 'confirm')
        self.assertEqual(result[0]['code'], 'ai_review_text')

    def test_mixed_issue_objects_and_strings_keep_order(self):
        result = _normalize_ai_issues([
            {'message': '계약일 확인', 'severity': 'block', 'code': 'date'},
            '통화 확인',
        ], 'error')
        self.assertEqual([x['message'] for x in result], ['계약일 확인', '통화 확인'])
        self.assertEqual(result[0]['severity'], 'block')
        self.assertEqual(result[1]['severity'], 'confirm')

    def test_invalid_issue_never_silently_disappears(self):
        for issue in (None, 17, [], ''):
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                _normalize_ai_issues([issue], 'error')

    def _example(self):
        snapshot = new_snapshot('sample', 'sale', 'ko')
        snapshot['revision'] = 4
        snapshot['clauses'] = [{'id': 'c1', 'order': 1, 'title': '서명',
                                'sentences': [{'id': 's1', 'text': '서명일: [서명 전 확인]'}]}]
        note = {'id': 'n1', 'contract_id': 'sample', 'base_revision': 4,
                'sentence_id': 's1', 'status': 'note', 'instruction': '서명일을 2026년 11월 9일로 수정'}
        return snapshot, note

    def test_valid_change_with_text_issue_builds_proposal_without_mutation(self):
        snapshot, note = self._example()
        old = deepcopy(snapshot)
        def fake_call(*args, **kwargs):
            return {'changes': [{'id': 'c', 'sentence_id': 's1',
                                 'original_text': '서명일: [서명 전 확인]',
                                 'proposed_text': '서명일: 2026년 11월 9일',
                                 'delete_sentence': False,
                                 'required_to_resolve_conflict': False}],
                    'issues': ['서명 장소는 확인 필요'], 'conflicts': []}
        with patch('Quotation_KEKOREA.contracts.service._call', side_effect=fake_call):
            result = propose_notes_revision(snapshot, [note], env={})
        self.assertEqual(result['base_revision'], 4)
        self.assertEqual(result['issues'][0]['severity'], 'confirm')
        self.assertEqual(snapshot, old)
        self.assertEqual(result['note_ids'], ['n1'])

    def test_bad_issue_does_not_mutate_revision_or_memo(self):
        snapshot, note = self._example()
        before = (deepcopy(snapshot), deepcopy(note))
        def fake_call(*args, **kwargs):
            return {'changes': [{'id': 'c', 'sentence_id': 's1',
                                 'original_text': '서명일: [서명 전 확인]',
                                 'proposed_text': '서명일: 2026년 11월 9일',
                                 'delete_sentence': False,
                                 'required_to_resolve_conflict': False}],
                    'issues': [None], 'conflicts': []}
        with patch('Quotation_KEKOREA.contracts.service._call', side_effect=fake_call):
            with self.assertRaises(ValueError):
                propose_notes_revision(snapshot, [note], env={})
        self.assertEqual((snapshot, note), before)
'''

note = '''## 2026-11-09 AI contract note review format recovery

- In `contracts/service.py`, AI issue lists containing plain nonempty text are normalized into explicit, unconfirmed review issues; invalid/empty content fails closed rather than disappearing.
- In `contracts/workspace.py`, the model receives clearer issue-structure instructions. Original sentence validation, conflict detection, and atomic revision approval remain unchanged.
- The BOX 3 final-revision-request error path explains that the contract has not changed and existing note drafts remain available.
- `tests/test_contract_review_issue_recovery.py` checks mixed/invalid issues, unmodified snapshots on failure, and correct proposal creation. FINAL still requires current-revision approval and existing placeholder/seal-authority checks.
'''

def replace_once(s, old, new, label):
    if new in s:
        return s
    if s.count(old) != 1:
        raise RuntimeError(f'{label} 예상 코드가 정확히 하나가 아닙니다 (count={s.count(old)}). 수정 전 사용자 코드를 확인해야 합니다.')
    return s.replace(old, new, 1)

updates = {}
service = (ROOT / SERVICE).read_text(encoding='utf-8-sig')
updates[SERVICE] = replace_once(service, NORMALIZER_OLD, NORMALIZER_NEW, str(SERVICE))
workspace = (ROOT / WORKSPACE).read_text(encoding='utf-8-sig')
updates[WORKSPACE] = replace_once(workspace, WORKSPACE_OLD, WORKSPACE_NEW, str(WORKSPACE))
ui = (ROOT / UI).read_text(encoding='utf-8-sig')
updates[UI] = replace_once(ui, UI_OLD, UI_NEW, str(UI))
updates[TEST] = TEST_TEXT
for readme in READMES:
    s = (ROOT / readme).read_text(encoding='utf-8-sig')
    updates[readme] = s if '## 2026-11-09 AI contract note review format recovery' in s else s.rstrip()+'\n\n'+note.strip()+'\n'

for p in (SERVICE, WORKSPACE, UI, TEST):
    ast.parse(updates[p], filename=str(p))

with tempfile.TemporaryDirectory(prefix='kekorea_review_install_') as tmp:
    root = Path(tmp)
    for p, content in updates.items():
        dest = root/p
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(content,encoding='utf-8')
    # Run independent strict normalizer checks using compiled function only; no external API.
    namespace = {}
    fn = next(n for n in ast.parse(updates[SERVICE]).body if isinstance(n, ast.FunctionDef) and n.name == '_normalize_ai_issues')
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<normalizer>','exec'),namespace)
    normalize=namespace['_normalize_ai_issues']
    assert normalize(['확인 필요'], 'error')[0]['severity']=='confirm'
    assert normalize([{'message':'A','severity':'block','code':'a'},'B'],'error')[1]['message']=='B'
    for invalid in (None,17,[],''):
        try: normalize([invalid],'error')
        except ValueError: pass
        else: raise AssertionError('An invalid issue was silently accepted')

changed=[p for p,content in updates.items() if not (ROOT/p).exists() or (ROOT/p).read_text(encoding='utf-8-sig')!=content]
if not changed:
    print('이미 설치된 변경사항입니다. 수정할 파일이 없습니다.')
    raise SystemExit(0)
backup_root=ROOT/'local_patch_backups'/('ai_review_fix_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
try:
    for p in changed:
        if (ROOT/p).exists():
            b=backup_root/p
            b.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/p,b)
    for p in changed:
        dest=ROOT/p
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(updates[p],encoding='utf-8')
except Exception:
    for p in changed:
        b=backup_root/p
        if b.exists():
            shutil.copy2(b,ROOT/p)
        elif (ROOT/p).exists():
            (ROOT/p).unlink()
    raise
print('설치 완료:',len(changed),'개 파일 변경')
print('백업 위치:',backup_root)
print('전체 앱 테스트 및 Streamlit 실동작은 아직 실행하지 않았습니다.')
