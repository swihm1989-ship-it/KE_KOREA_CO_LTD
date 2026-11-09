"""Idempotent, fail-closed patch for KE KOREA shared reference promotion.

Run from repository root: python kekorea_shared_library_bridge/apply_shared_library_bridge.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
UI = ROOT / 'Quotation_KEKOREA/contracts/library_ui.py'
MODULE = ROOT / 'Quotation_KEKOREA/contracts/promote_reference.py'
TEST = ROOT / 'Quotation_KEKOREA/tests/test_contract_shared_reference_promotion.py'
DOCS = [ROOT/'README.md', ROOT/'Quotation_KEKOREA/README.md',
        ROOT/'Quotation_KEKOREA/README_CONTRACTS.md',
        ROOT/'Quotation_KEKOREA/Team/README.md',
        ROOT/'Quotation_KEKOREA/Presentation/README.md']

IMPORT_ANCHOR = 'from Quotation_KEKOREA.contracts.repository import ContractRepositoryError\n'
AFTER_ANCHOR = "        st.caption('원본과 추출 내용은 관리자 전용입니다. 검색에는 승인한 익명화 참고 메모만 사용됩니다.')\n"
INSERT = '''        # Explicitly promote a previously saved per-contract reference. Admin-only.
        # No source deletion and no AI retrieval before reviewed guidance approval.
        current_contract_id = st.session_state.get('contract_active_id')
        if current_contract_id:
            with st.expander('현재 계약의 참고자료를 공통 라이브러리에 등록', expanded=False):
                references = [r for r in repo.contract_references(current_contract_id)
                              if str(r.get('filename') or '').lower().endswith(('.pdf', '.docx'))]
                if not references:
                    st.caption('현재 계약에 등록된 PDF/DOCX 참고자료가 없습니다.')
                else:
                    options = {str(r['id']): r for r in references}
                    with st.form(f'promote_contract_reference_{current_contract_id}'):
                        selected = st.selectbox('공통 등록할 기존 참고자료', list(options),
                                                format_func=lambda v: options[v].get('filename', v))
                        common_title = st.text_input('공통 라이브러리 표시 제목 (거래처·개인정보 제외)')
                        common_types = st.multiselect('재사용할 계약 유형',
                                                      ['sale', 'trade_commission', 'investment_commission'])
                        common_language = st.selectbox('참고자료 언어', ['ko', 'en'])
                        confirmed = st.checkbox('회사 공통 재사용에 적합한 자료이며, 원본은 관리자만 열람하고 승인 전 AI 검색에 사용하지 않는 데 동의합니다.')
                        do_promote = st.form_submit_button('공통 라이브러리에 승인 대기로 등록')
                    if do_promote:
                        try:
                            if not confirmed or not common_title.strip() or not common_types:
                                raise ValueError('명시적 동의, 공통 제목, 계약 유형을 모두 입력해 주세요.')
                            record = promote_contract_reference(
                                repo, current_contract_id, selected, title=common_title,
                                contract_types=common_types, language=common_language)
                            st.success('공통 라이브러리에 승인 대기로 등록했습니다. 아래에서 익명화 메모를 검토·승인해야 다른 계약의 AI 검색에 활용됩니다.')
                            st.rerun()
                        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                            st.error(str(exc))
'''
MARKER = 'KE KOREA 공통 참고자료 승격 / 2026-11-09'
DOC_NOTE = (
    '\n\n### ' + MARKER + '\n'
    '- 계약별로 비공개 저장된 참고 PDF/DOCX는 그대로 유지한다. 관리 키 인증을 마친 관리자만 현재 계약의 기존 참고자료를 회사 공통 샘플 라이브러리에 명시적으로 등록할 수 있다.\n'
    '- 원본 해시 및 현재 계약 소속을 확인하여 Supabase 비공개 `kekorea-contracts` 라이브러리 경로에 별도 등록하고, 공통 레코드는 `kekorea_contract_references`에서 `contract_id=NULL`, `library_pending`으로 보관한다. 다른 계약의 원본 파일을 자동으로 공개하거나 이전하지 않는다.\n'
    '- 원본 등록만으로 AI 장기기억 또는 자동학습이 되는 것이 아니다. 관리자 검토 후 개인정보·회사명·거래 금액·계좌 등을 제거한 익명화 참고 메모를 명시적으로 승인해야 검색·RAG에서 계약 유형에 맞춰 재사용한다.\n'
    '- 기존 `library.py`/`repository.py`/`service.py`, 계약의 PDF/Word 생성, ECLADO 및 PO/PI/CI/PL 기능은 변경하지 않는다. 인증되지 않은 운영 공개화면에서 원본을 공유해서는 안 된다.\n'
)


def main():
    if not UI.is_file() or any(not doc.is_file() for doc in DOCS):
        raise SystemExit('프로젝트 루트에 폴더를 넣었는지 확인하세요. 필요한 파일이 없습니다.')
    source = UI.read_text(encoding='utf-8')
    if '현재 계약의 참고자료를 공통 라이브러리에 등록' in source:
        raise SystemExit('이미 적용된 기능입니다. 다시 실행하지 마세요.')
    if source.count(IMPORT_ANCHOR) != 1 or source.count(AFTER_ANCHOR) != 1:
        raise SystemExit('최신 library_ui.py 구조가 예상과 다릅니다. 덮어쓰지 않고 중단합니다.')
    if MODULE.exists() or TEST.exists():
        raise SystemExit('같은 이름의 모듈 또는 테스트가 이미 있습니다. 덮어쓰기 전에 확인하세요.')
    # Prepare before modifying any files.
    modified = source.replace(IMPORT_ANCHOR,
        IMPORT_ANCHOR + 'from Quotation_KEKOREA.contracts.promote_reference import promote_contract_reference\n', 1)
    modified = modified.replace(AFTER_ANCHOR, AFTER_ANCHOR + INSERT, 1)
    compile(modified, str(UI), 'exec')
    for path in (HERE/'promote_reference.py', HERE/'test_shared_library_bridge.py'):
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
    changed_docs = {}
    for doc in DOCS:
        body = doc.read_text(encoding='utf-8')
        if MARKER in body:
            raise SystemExit(f'이미 README가 갱신됐습니다: {doc}')
        changed_docs[doc] = body.rstrip() + DOC_NOTE
    backup = HERE / ('backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    for original in [UI] + DOCS:
        target = backup / original.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    UI.write_text(modified, encoding='utf-8')
    shutil.copy2(HERE/'promote_reference.py', MODULE)
    shutil.copy2(HERE/'test_shared_library_bridge.py', TEST)
    for doc, body in changed_docs.items():
        doc.write_text(body, encoding='utf-8')
    print('적용 완료: 공통 라이브러리 승격 기능 + 단위 테스트 + README 5개')
    print('백업 위치:', backup)
    print('GitHub 커밋/푸시/배포는 자동으로 수행하지 않았습니다.')


if __name__ == '__main__':
    main()
