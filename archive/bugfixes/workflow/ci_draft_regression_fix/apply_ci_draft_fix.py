"""Restore CI DRAFT exports, retain PO/PI checks, and synchronize five READMEs."""
from pathlib import Path
import ast

root = Path(__file__).resolve().parent.parent
app = root / 'Quotation_KEKOREA' / 'app.py'
old = 'export_blocked = bool(unconfirmed_product_matches or pending_review_fields or financial_blockers or bank_blockers or seal_blockers or'
new = 'export_blocked = bool((expected_type in {"PO", "PI"} and unconfirmed_product_matches) or pending_review_fields or financial_blockers or bank_blockers or seal_blockers or'
notes = {
    'README.md': '2026-11-06 CI 회귀 보완: PO/PI는 확인이 필요한 제품 주석이 남으면 PDF/Excel 생성을 차단합니다. CI는 원본 PI 거래가격을 유지하며, 상품명 매칭이 미확정인 경우 경고 및 DRAFT 표시를 전제로 검토용 파일 생성을 허용합니다.',
    'Quotation_KEKOREA/README.md': '''### 2026-11-06 CI 검토용 DRAFT 출력 회귀 보완

PO/PI에서 확인이 필요한 상품 주석은 문서 생성 전에 확인해야 합니다. CI는 기존처럼 첨부 PI의 실제 거래가격를 유지하고 상품명 매칭이 미확정이면 경고 및 DRAFT 상태를 표시한 채 검토용 PDF/Excel 생성을 허용합니다. `test_review_ui.py::test_unconfirmed_ci_product_match_allows_draft_pdf`와 `test_product_matching_ui.py`의 동작을 함께 유지합니다. 실제 테스트 결과는 실행 후 기록하며, 최종 발행·전송을 자동 수행하지 않습니다.''',
    'Quotation_KEKOREA/README_CONTRACTS.md': '''## 2026-11-06 CI regression scope

The document-export safeguard is document-specific: PO/PI product-annotation confirmation blocks PDF/Excel generation; a CI preserving attached-PI transaction prices may produce an explicitly marked DRAFT with unresolved product matching warnings. This CI rule does not relax contract-export validation or change commission clauses.''',
    'Quotation_KEKOREA/Team/README.md': '''## 2026-11-06 CI DRAFT 출력 보존

PO/PI의 확인 전 생성 차단과 달리, CI는 첨부 PI 거래가격을 변경하지 않고 상품 매칭 미확정 경고 및 DRAFT 상태를 유지해 검토용 PDF/Excel 출력을 허용합니다. 관련 회귀 테스트는 `test_product_matching_ui.py`와 `test_review_ui.py`이며 둘 다 통과해야 합니다.''',
    'Quotation_KEKOREA/Presentation/README.md': '''## 2026-11-06 CI DRAFT 시연 주의

상품 검증이 필요한 PO/PI는 확인 전 생성 버튼이 차단됩니다. CI는 첨부 PI 가격을 보존하는 조건에서 미확정 상품을 경고로 표시한 검토용 DRAFT 파일을 만들 수 있습니다. 검토용 출력은 최종 승인·발행이 아니며 테스트 및 실제 배포 확인 여부를 구분해 설명합니다.''',
}
if not app.is_file():
    raise SystemExit('프로젝트 루트에 ci_draft_regression_fix 폴더를 배치하세요.')
for rel in notes:
    if not (root / rel).is_file():
        raise SystemExit(f'필수 README가 없습니다: {rel}')
source = app.read_text(encoding='utf-8')
if old in source:
    if source.count(old) != 1:
        raise SystemExit('변경 지점이 하나가 아니어서 중단합니다.')
    updated = source.replace(old, new, 1)
    ast.parse(updated)
    app.write_text(updated, encoding='utf-8')
    print('app.py: PO/PI 확인 보호 유지, CI DRAFT 출력 복원.')
elif new in source:
    print('app.py: 이미 수정되어 있습니다.')
else:
    raise SystemExit('예상한 생성 차단 코드가 없습니다. 안전을 위해 중단합니다.')
for rel, block in notes.items():
    path = root / rel
    contents = path.read_text(encoding='utf-8')
    if block.strip() not in contents:
        path.write_text(contents.rstrip() + '\n\n' + block.strip() + '\n', encoding='utf-8')
        print('README updated:', rel)
print('적용 완료. 테스트 OK 전에는 push하지 마세요.')
