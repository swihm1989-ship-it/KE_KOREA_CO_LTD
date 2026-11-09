"""Apply KE KOREA contract-note schema and final preview fixes safely.
Run from repository root: python ./kekorea_final_revision_integrated/apply_fix.py
"""
from __future__ import annotations
import ast
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
FILES = [
    'Quotation_KEKOREA/contracts/service.py',
    'Quotation_KEKOREA/contracts/workspace.py',
    'Quotation_KEKOREA/contracts/ui.py',
    'Quotation_KEKOREA/tests/test_contract_review_flow_regression.py',
    'README.md',
    'Quotation_KEKOREA/README.md',
    'Quotation_KEKOREA/README_CONTRACTS.md',
    'Quotation_KEKOREA/Team/README.md',
    'Quotation_KEKOREA/Presentation/README.md',
]
REQUIRED = [x for x in FILES if not x.endswith('test_contract_review_flow_regression.py')]
MARKER = '2026-11-09 - BOX 3 AI review issue normalization and approved revision preview'


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected 1 matching block; found {n}. No files changed. Attach current source for a tailored fix.')
    return text.replace(old, new, 1)


def patch_service(source):
    if 'AI issue string converted to review issue' in source:
        return source
    old = '''    normalized = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("Contract AI returned an invalid review issue.")
        candidate = dict(issue)
        message = candidate.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Contract AI returned a review issue without a message.")'''
    new = '''    normalized = []
    for index, issue in enumerate(issues, start=1):
        # AI issue string converted to review issue; preserve the warning rather
        # than discarding an otherwise valid clause revision.
        if isinstance(issue, str) and issue.strip():
            candidate = {"message": issue.strip(), "severity": "confirm",
                         "code": "ai_review", "id": f"ai_review_{uuid4().hex}"}
        elif isinstance(issue, dict):
            candidate = dict(issue)
            if not isinstance(candidate.get("message"), str) or not candidate.get("message", "").strip():
                alternative = next((candidate.get(field) for field in ("description", "detail", "text")
                                    if isinstance(candidate.get(field), str) and candidate[field].strip()), None)
                if alternative:
                    candidate["message"] = alternative.strip()
        else:
            raise ValueError(f"AI 검토사항 {index}번의 형식이 올바르지 않습니다. 기존 계약과 메모는 보존됐습니다.")
        message = candidate.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError(f"AI 검토사항 {index}번에 설명이 없습니다. 기존 계약과 메모는 보존됐습니다.")'''
    return replace_once(source, old, new, 'service issue normalization')


def patch_workspace(source):
    if 'Every item in issues MUST be an object' in source:
        return source
    old = "'otherwise return conflicts as an empty list. Return JSON keys explanation, changes, issues, conflicts. '"
    new = ("'otherwise return conflicts as an empty list. Return JSON keys explanation, changes, issues, conflicts. '"
           "'Every item in issues MUST be an object with nonempty message and severity of block, confirm or info; '"
           "'use an empty list when there are no issues, never a bare string or list of strings. '")
    return replace_once(source, old, new, 'workspace AI response contract')


def patch_ui(source):
    # The original contract UI already has a revision-approval panel; extend it,
    # never replace the revision engine, checkbox approval, or FINAL safeguards.
    if 'contract_full_preview_ready_' in source:
        return source
    old = '''    col_apply, col_cancel = st.columns(2)
    if col_apply.button("선택한 변경을 하나의 revision으로 적용",'''
    new = '''    if selected_ids and not stale and batch_reviewed:
        try:
            candidate_preview = apply_proposal(snapshot, proposal, selected_ids)
        except (ValueError, RevisionConflict) as preview_error:
            st.error("수정안 미리보기 검증 실패: " + str(preview_error))
        else:
            with st.expander("선택한 수정 적용 후 계약서 전체 미리보기", expanded=True):
                st.caption("아직 저장되지 않은 미리보기입니다. 아래 승인 버튼을 눌러야 revision으로 저장됩니다.")
                for preview_clause in candidate_preview.get('clauses', []):
                    st.markdown("**" + str(preview_clause.get('title') or '계약 조항') + "**")
                    for preview_sentence in preview_clause.get('sentences', []):
                        st.write(str(preview_sentence.get('text') or ''))
                preview_blockers = final_document_blockers(candidate_preview)
                if preview_blockers:
                    st.warning(f"FINAL 생성 전에 해결할 항목 {len(preview_blockers)}건이 남아 있습니다.")
                    for blocker in preview_blockers:
                        st.write("• " + blocker)
                else:
                    st.success("본문의 FINAL 차단 사항이 해결됐습니다. 승인 저장 후 직인 권한 및 최종 파일을 확인하세요.")
    col_apply, col_cancel = st.columns(2)
    if col_apply.button("선택한 변경을 하나의 revision으로 적용",'''
    source = replace_once(source, old, new, 'approved revision preview before applying')
    old = '''            st.session_state[state_key] = saved
            st.session_state.pop("contract_pending_proposal", None)'''
    new = '''            st.session_state[state_key] = saved
            st.session_state[f"contract_full_preview_ready_{snapshot['contract_id']}"] = saved['revision']
            st.session_state.pop("contract_pending_proposal", None)'''
    source = replace_once(source, old, new, 'approval marks full preview ready')
    old = """def _export_panel(repo, snapshot, env):
    st.markdown('#### 문서 다운로드')"""
    new = """def _export_panel(repo, snapshot, env):
    if st.session_state.get(f"contract_full_preview_ready_{snapshot['contract_id']}") == snapshot['revision']:
        with st.expander("승인·저장된 최종 수정 계약서 전체 미리보기", expanded=True):
            st.caption(f"저장 완료: Revision {snapshot['revision']} · 아래 내용은 현재 저장된 BOX 3의 본문입니다.")
            for preview_clause in snapshot.get('clauses', []):
                st.markdown("**" + str(preview_clause.get('title') or '계약 조항') + "**")
                for preview_sentence in preview_clause.get('sentences', []):
                    st.write(str(preview_sentence.get('text') or ''))
            remaining = final_document_blockers(snapshot)
            if remaining:
                st.warning(f"아직 FINAL PDF를 만들 수 없습니다. 확인할 항목 {len(remaining)}건:")
                for blocker in remaining:
                    st.write("• " + blocker)
            else:
                st.success("본문 차단 항목이 모두 해결됐습니다. 최종 승인 및 직인 권한 확인 후 FINAL을 생성할 수 있습니다.")
    st.markdown('#### 문서 다운로드')"""
    source = replace_once(source, old, new, 'saved revision full preview')
    old = """        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))


def _review_panel(repo, snapshot, state_key, issues):"""
    new = """        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error('AI 수정안 생성에 실패했습니다. 입력한 메모와 저장된 계약 내용은 보존됩니다: ' + str(exc))
            st.info('메모를 다시 작성하지 말고, AI 응답 형식과 앱 배포 버전을 확인한 뒤 재시도하세요.')


def _review_panel(repo, snapshot, state_key, issues):"""
    source = replace_once(source, old, new, 'failure preserves notes feedback')
    return source


def append_readme(text, path):
    if MARKER in text:
        return text
    role = {
        'README.md': 'UI 수정 흐름: 메모를 저장한 뒤 수정안 비교 및 승인 시 전체 계약서 미리보기를 제공한다. AI가 문자열로 반환한 검토 쟁점은 확인 필요 항목으로 보존하고, 불명확한 항목은 설명과 함께 거부한다.',
        'Quotation_KEKOREA/README.md': '계약서 작성 UI에서 최종 수정 요청은 AI 제안 단계다. 변경 전후를 비교하고 하나의 revision으로 승인해야 계약 본문에 반영된다. 승인 직후 저장된 전체 계약서 미리보기를 표시한다.',
        'Quotation_KEKOREA/README_CONTRACTS.md': 'contracts/service.py normalizes nonempty string AI issues as confirm-level issues without removing unresolved legal checks. contracts/workspace.py requests structured issues. contracts/ui.py shows dry-run and committed full-clause previews. FINAL remains blocked for authored placeholders, unreconciled changes and missing required parties.',
        'Quotation_KEKOREA/Team/README.md': '최종 수정 요청 실패 시 기존 문장별 메모는 남는다. 비교 화면에서 선택한 수정안을 승인하면 revision이 생성되고 최신 BOX 3 본문 전체가 미리보기에 표시된다. 남은 임시 문구는 구체적으로 안내하며 자동으로 제거하지 않는다.',
        'Quotation_KEKOREA/Presentation/README.md': '개선 시나리오: 메모 6건 → AI 검토사항 형식 정상화 → 수정 전후 비교·전체 미리보기 → 수정안 승인 → 저장된 최신 계약서 미리보기 → 남은 조건 확인 후 FINAL PDF. 자동 날인이나 임시 문구 우회 없음.',
    }[path]
    return text.rstrip() + '\n\n## ' + MARKER + '\n\n- ' + role + '\n'


def main():
    if not all((ROOT / path).is_file() for path in REQUIRED):
        missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
        raise SystemExit(f'프로젝트 최상위 폴더에서 실행하세요. 누락: {missing}')
    original = {p: (ROOT / p).read_text(encoding='utf-8-sig') for p in REQUIRED}
    edits = dict(original)
    try:
        edits['Quotation_KEKOREA/contracts/service.py'] = patch_service(original['Quotation_KEKOREA/contracts/service.py'])
        edits['Quotation_KEKOREA/contracts/workspace.py'] = patch_workspace(original['Quotation_KEKOREA/contracts/workspace.py'])
        edits['Quotation_KEKOREA/contracts/ui.py'] = patch_ui(original['Quotation_KEKOREA/contracts/ui.py'])
        for path in REQUIRED:
            if path.endswith('README.md') or path in ('README.md', 'Quotation_KEKOREA/README_CONTRACTS.md'):
                edits[path] = append_readme(original[path], path)
        for path in edits:
            if path.endswith('.py'):
                ast.parse(edits[path], filename=path)
        # Independent code-path self-check for JSON issue handling without importing the app.
        module = ast.parse(edits['Quotation_KEKOREA/contracts/service.py'])
        fn = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == '_normalize_ai_issues')
        ns = {'uuid4': __import__('uuid').uuid4}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<normalizer>', 'exec'), ns)
        normalizer = ns['_normalize_ai_issues']
        sample = normalizer(['계약일 확인 필요', {'code':'legal', 'severity':'block', 'message':'준거법 확인'}], 'invalid')
        assert sample[0]['severity'] == 'confirm' and sample[0]['message'] == '계약일 확인 필요'
        assert sample[1]['severity'] == 'block'
        try:
            normalizer([None], 'invalid')
        except ValueError:
            pass
        else:
            raise AssertionError('null issues must fail closed')
    except Exception as exc:
        raise SystemExit('검증 실패: 사용자 파일은 변경되지 않았습니다.\n' + str(exc)) from exc

    changed = [path for path in REQUIRED if edits[path] != original[path]]
    if not changed:
        print('이미 설치된 상태입니다. 변경 없음.')
        return
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = ROOT / 'local_patch_backups' / ('review_flow_' + stamp)
    for path in changed:
        destination = backup / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, destination)
    written = []
    try:
        for path in changed:
            (ROOT / path).write_text(edits[path], encoding='utf-8')
            written.append(path)
        test_src = Path(__file__).with_name('test_contract_review_flow_regression.py')
        target = ROOT / 'Quotation_KEKOREA/tests/test_contract_review_flow_regression.py'
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(test_src, target)
            written.append('Quotation_KEKOREA/tests/test_contract_review_flow_regression.py')
    except Exception:
        for path in changed:
            shutil.copy2(backup / path, ROOT / path)
        raise SystemExit('쓰기 실패, 변경된 소스파일을 백업에서 복원했습니다.')
    print('수정 성공:')
    for p in written:
        print('  '+p)
    print('기존 파일 백업:', backup)
    print('GitHub 푸시 및 Streamlit 재배포는 별도로 필요합니다.')


if __name__ == '__main__':
    main()
