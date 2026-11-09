"""Move contract verification details out of the primary download path.

Does not change validate_rules, confirmation state, export engine, or any trade code.
Run from KE_KOREA_CO_LTD repository root with python path/to/script.py.
"""
from pathlib import Path
import ast
import shutil
from datetime import datetime

ROOT = Path.cwd()
UI = ROOT / 'Quotation_KEKOREA/contracts/ui.py'
DOCS = [
    ROOT / 'README.md',
    ROOT / 'Quotation_KEKOREA/README.md',
    ROOT / 'Quotation_KEKOREA/README_CONTRACTS.md',
    ROOT / 'Quotation_KEKOREA/Team/README.md',
    ROOT / 'Quotation_KEKOREA/Presentation/README.md',
]
OLD_HEAD = '''    _review_panel(repo, snapshot, f"contract_snapshot_{snapshot['contract_id']}", issues)
    st.markdown("#### 문서 다운로드")
    st.caption("DRAFT는 미확정을 표시한 검토용입니다. FINAL은 기존 최종 검증을 통과해야 생성할 수 있습니다.")'''
NEW_HEAD = '''    st.markdown("#### 문서 다운로드")
    st.caption("검토용 DRAFT PDF/Word는 미확정 정보가 있어도 만들 수 있습니다. "
               "FINAL은 필수 조건을 실제로 확인해야 생성됩니다. 검토 목록을 숨겨도 최종 검증 결과는 달라지지 않습니다.")'''
OLD_FINAL = '''            if mode == 'final' and issues:
                st.caption("필수 확인이 남아 있습니다. 위 검토 메뉴에서 수정 위치를 확인하세요.")'''
NEW_FINAL = '''            if mode == 'final' and issues:
                st.caption(f"최종 확인이 필요한 항목 {len(issues)}건. BOX 2에서 실제 조건을 입력·확정하고, "
                           "필요하면 아래 '고급 검토 기록'에서 AI 쟁점 근거를 확인하세요.")'''
OLD_REVIEW = 'with st.expander("서명 전 검토 · 필요한 항목만 확인", expanded=False):'
NEW_REVIEW = 'with st.expander("고급 검토 기록 · 확정 근거 확인 (선택)", expanded=False):'
TAIL_MARKER = '''                    except ContractRepositoryError as exc:
                        st.error(str(exc))


def _contract_mime(extension):'''
TAIL_REPLACEMENT = '''                    except ContractRepositoryError as exc:
                        st.error(str(exc))
    # Optional audit/reconciliation controls are still reachable, but never
    # interrupt DRAFT download or masquerade as the FINAL export validator.
    _review_panel(repo, snapshot, f"contract_snapshot_{snapshot['contract_id']}", issues)


def _contract_mime(extension):'''
DOC_NOTE = (
    '\n\n### 2026-11-06 계약서 내보내기 UI 간소화 (검증 규칙 변경 없음)\n\n'
    '- BOX 3에서 문서 다운로드(DRAFT/FINAL)를 먼저 표시하고, 길게 반복되는 서명 전 검토 목록은 '
    '`고급 검토 기록 · 확정 근거 확인 (선택)` 접힌 영역으로 이동했다. 검토 기록·원문·확인 근거 입력 기능은 유지한다.\n'
    '- 미확정 조건이 있더라도 검토용 DRAFT PDF/DOCX는 생성할 수 있다. '
    'FINAL PDF/DOCX는 변경하지 않은 기존 `validate_rules(..., for_export=True)` 결과에 따라 차단될 수 있다. '
    'UI를 숨기거나 TBD를 선택하는 것이 법적/거래조건 확인을 의미하지는 않는다.\n'
    '- 계약서 UI 외의 ECLADO·PO/PI/CI/PL, 지급정책, 수정 엔진, 저장·승인 로직은 수정하지 않는다. '
    '실제 Streamlit 운영 화면과 전체 회귀 테스트는 사용자 PC에서 별도로 검증한다.\n'
)

def once(text, before, after, label):
    if text.count(before) != 1:
        raise RuntimeError(f'Cannot safely update {label}: expected anchor exactly once, found {text.count(before)}')
    return text.replace(before, after, 1)


def main():
    if not UI.is_file() or any(not p.is_file() for p in DOCS):
        raise RuntimeError('Run from the KE_KOREA_CO_LTD repository root; project or README files missing.')
    original = UI.read_text(encoding='utf-8')
    if NEW_HEAD in original or NEW_REVIEW in original:
        raise RuntimeError('This patch appears already applied. No files were modified.')
    updated = once(original, OLD_HEAD, NEW_HEAD, 'download heading')
    updated = once(updated, OLD_FINAL, NEW_FINAL, 'final guidance')
    updated = once(updated, OLD_REVIEW, NEW_REVIEW, 'advanced review heading')
    updated = once(updated, TAIL_MARKER, TAIL_REPLACEMENT, 'advanced review relocation')
    # Preserve existing FINAL and DRAFT gating exactly.
    required = ('issues = validate_rules(snapshot, for_export=True, env=env)',
                'disabled=bool(issues) if mode == \'final\' else False',
                'if mode == \'final\' and validate_rules(snapshot, for_export=True, env=env):')
    if not all(s in updated for s in required):
        raise RuntimeError('Export validation guard was unexpectedly modified; aborting.')
    if updated.count('    _review_panel(repo, snapshot, f"contract_snapshot_{snapshot[\'contract_id\']}", issues)') != 1:
        raise RuntimeError('Review panel count changed; aborting.')
    ast.parse(updated, filename=str(UI))
    doc_data = {}
    for p in DOCS:
        raw = p.read_text(encoding='utf-8')
        if '### 2026-11-06 계약서 내보내기 UI 간소화 (검증 규칙 변경 없음)' in raw:
            raise RuntimeError(f'Already documented in {p}; no files modified.')
        doc_data[p] = raw.rstrip() + '\n' + DOC_NOTE
    backup = ROOT / 'kekorea_export_review_cleanup_backup' / datetime.now().strftime('%Y%m%d_%H%M%S')
    for p in [UI, *DOCS]:
        destination = backup / p.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, destination)
    UI.write_text(updated, encoding='utf-8')
    for p, value in doc_data.items():
        p.write_text(value, encoding='utf-8')
    print('Updated contract download presentation. Existing export validation intact.')
    print('Updated five READMEs. Backup:', backup)
    print('Next: run contract/full regression tests and git diff --check. Do not push before testing.')

if __name__ == '__main__':
    main()
