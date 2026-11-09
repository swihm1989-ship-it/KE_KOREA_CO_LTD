from pathlib import Path
import shutil
from datetime import datetime

root = Path(__file__).resolve().parent.parent
ui = root / 'Quotation_KEKOREA/contracts/ui.py'
if not ui.is_file():
    raise SystemExit('프로젝트 루트에 패치 폴더를 복사한 다음 실행하세요.')
original = ui.read_text(encoding='utf-8')
marker = '    /* Contract sentence alignment: consistent left edge for short and long clauses. */'
if marker in original:
    print('문장 정렬 패치가 이미 적용되어 있습니다. 중복 적용하지 않았습니다.')
    raise SystemExit(0)
anchor = '    /* Long clause readability: never shrink below a usable font size or clip text. */'
if original.count(anchor) != 1:
    raise SystemExit('현재 ui.py CSS가 예상 코드와 다릅니다. 기존 파일을 변경하지 않았습니다.')
css = '''    /* Contract sentence alignment: consistent left edge for short and long clauses. */
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button {
        justify-content:flex-start!important;text-align:left!important;
        align-items:flex-start!important;flex-direction:row!important;
    }
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] {
        width:100%!important;min-width:0!important;text-align:left!important;
        margin:0!important;padding:0!important;
    }
    .st-key-contract_document_paper [class*="st-key-contract_sentence_display_"] [data-testid="stButton"] button p {
        width:100%!important;max-width:none!important;min-width:0!important;
        margin:0!important;padding:0!important;text-align:left!important;
    }
'''
updated = original.replace(anchor, css+anchor, 1)
backupdir = root / ('kekorea_alignment_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backupdir.mkdir()
shutil.copy2(ui, backupdir/'ui.py')
ui.write_text(updated,encoding='utf-8')
readmes = [root/'README.md',root/'Quotation_KEKOREA/README.md',root/'Quotation_KEKOREA/README_CONTRACTS.md',root/'Quotation_KEKOREA/Team/README.md',root/'Quotation_KEKOREA/Presentation/README.md']
entry = '\n\n### BOX 3 문장 정렬 보정 (2026-11-09)\n계약서 미리보기의 모든 문장 버튼과 내부 텍스트 래퍼를 동일한 왼쪽 기준선으로 정렬한다. 짧은 문장/긴 문장의 시작점이 일치하며, 기존 자동 줄바꿈·문장 호버 전체보기·문장별 메모·AI 수정과 계약서 저장/출력 검증은 변경하지 않는다. 수정 파일: `Quotation_KEKOREA/contracts/ui.py` (CSS만).\n'
for p in readmes:
    if not p.exists():
        print('README 없음, 건너뜀:',p)
        continue
    text=p.read_text(encoding='utf-8')
    if '### BOX 3 문장 정렬 보정 (2026-11-09)' not in text:
        (backupdir/(p.name+'.'+str(len(list(backupdir.iterdir()))))).write_text(text,encoding='utf-8')
        p.write_text(text.rstrip()+entry,encoding='utf-8')
print('적용 완료. BOX 3 문장 정렬 CSS 및 README 5개 갱신. 백업:',backupdir)
