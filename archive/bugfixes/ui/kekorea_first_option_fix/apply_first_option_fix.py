"""Narrow, idempotent patch for selected AI risk option button.
Run at KE_KOREA_CO_LTD repository root.
"""
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path.cwd()
UI = ROOT / 'Quotation_KEKOREA/contracts/risk_review_ui.py'
BEFORE = "if st.button('이 추천안 선택', key=f'risk_choose_{contract_id}_{revision}_{sentence_id}_{index}',\n                              disabled=picked):"
AFTER = "if st.button('이 추천안 선택', key=f'risk_choose_{contract_id}_{revision}_{sentence_id}_{index}',\n                              type='primary' if picked else 'secondary'):"
DOCS = [
    'README.md',
    'Quotation_KEKOREA/README.md',
    'Quotation_KEKOREA/README_CONTRACTS.md',
    'Quotation_KEKOREA/Team/README.md',
    'Quotation_KEKOREA/Presentation/README.md',
]
MARKER = 'AI 위험 검토 추천안 기본 선택 버튼 보완'
NOTE = ('\n\n### ' + MARKER + '\n'
        '- `Quotation_KEKOREA/contracts/risk_review_ui.py`에서 기본 선택된 추천안 1번도 다시 선택할 수 있도록 `disabled=picked` 조건을 제거했다.\n'
        '- 선택된 추천안은 `primary`, 다른 추천안은 `secondary` 스타일로 표시한다. 추천 문구·변수 편집·미리보기·승인·PDF/Word 검증은 변경하지 않았다.\n')

def main():
    if not UI.is_file():
        raise SystemExit('오류: 프로젝트 루트에서 실행하세요. risk_review_ui.py를 찾지 못했습니다.')
    source = UI.read_text(encoding='utf-8')
    if AFTER in source and BEFORE not in source:
        print('이미 적용된 코드입니다. 중복 적용하지 않습니다.')
        return
    if source.count(BEFORE) != 1:
        raise SystemExit('중단: 예상 코드가 정확히 한 번 발견되지 않습니다. 기존 파일은 수정하지 않았습니다.')
    missing = [str(x) for x in DOCS if not (ROOT / x).is_file()]
    if missing:
        raise SystemExit('중단: README가 없습니다: ' + ', '.join(missing))
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = ROOT / ('kekorea_first_option_backup_' + stamp)
    backup.mkdir(exist_ok=False)
    for name in [str(UI.relative_to(ROOT)), *DOCS]:
        dest = backup / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    new_source = source.replace(BEFORE, AFTER, 1)
    compile(new_source, str(UI), 'exec')
    UI.write_text(new_source, encoding='utf-8')
    for name in DOCS:
        file = ROOT / name
        old = file.read_text(encoding='utf-8')
        if MARKER not in old:
            file.write_text(old.rstrip() + '\n' + NOTE, encoding='utf-8')
    print('선택 버튼 수정 완료. 기존 5개 README에 변경사항을 기록했습니다.')
    print('원본 백업:', backup)

if __name__ == '__main__':
    main()
