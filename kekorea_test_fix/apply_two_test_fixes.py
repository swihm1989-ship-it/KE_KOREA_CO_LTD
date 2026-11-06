from pathlib import Path
import ast
from datetime import date

root = Path(__file__).resolve().parent.parent
app = root / 'Quotation_KEKOREA/app.py'
policy = root / 'Quotation_KEKOREA/contracts/commission_policy.py'
if not app.exists() or not policy.exists():
    raise SystemExit('Project root not found. Place kekorea_test_fix in KE_KOREA_CO_LTD project root.')

changes = []
app_text = app.read_text(encoding='utf-8')
old = 'export_blocked = bool(pending_review_fields or financial_blockers or bank_blockers or seal_blockers or'
new = 'export_blocked = bool(unconfirmed_product_matches or pending_review_fields or financial_blockers or bank_blockers or seal_blockers or'
if old not in app_text:
    if new not in app_text:
        raise SystemExit('Unexpected app.py layout; stopping before editing. Need manual review.')
else:
    assert app_text.count(old) == 1
    modified = app_text.replace(old,new,1)
    ast.parse(modified)
    changes.append((app,modified))

policy_text = policy.read_text(encoding='utf-8')
old = 'f\'within {days} calendar days after that Trigger (D+{days}). Where actual receipt is the agreed Trigger, \''
new = 'f\'within {"seven (7)" if days == 7 else str(days)} calendar days after that Trigger (D+{days}). Where actual receipt is the agreed Trigger, \''
if old not in policy_text:
    if new not in policy_text:
        raise SystemExit('Unexpected commission_policy.py layout; stopping before editing. Need manual review.')
else:
    assert policy_text.count(old) == 1
    modified = policy_text.replace(old,new,1)
    ast.parse(modified)
    changes.append((policy,modified))

notes = {
'README.md': '\n### 2026-11-06 검증 보완\n\n계약 수수료 기본 D+7 영문 조항은 `seven (7) calendar days` 표기를 유지하며, 사용자 지정 기간은 해당 일수를 출력합니다. PO/PI 상품명에 확인이 필요한 주석이 남아 있으면 PDF/Excel 생성 버튼을 비활성화합니다. 관련 상세 사항과 검증 방법은 `Quotation_KEKOREA/README.md`를 참조합니다.\n',
'Quotation_KEKOREA/README.md': '\n### 2026-11-06 전체 테스트 실패 2건 수정\n\n- 계약 커미션 기본 7일 기한을 영문 `seven (7) calendar days`로 표기해 법률 문서의 기존 기본 문구와 테스트를 일치시켰습니다. 7일이 아닌 명시적 사용자 지급기한은 그대로 반영합니다.\n- 상품명 주석 확인(`Confirm product annotation` 및 `Double-check this product`)이 남은 PO/PI에서는 PDF/Excel 생성 버튼을 차단합니다. 체크박스 확인 후에만 생성을 허용합니다. 가격 자동 조회 및 상품명 원문 보존 규칙은 변경하지 않았습니다.\n- 회귀 검사: `tests/test_commission_policy.py`, `tests/test_product_matching_ui.py`; 전체 테스트는 아래 명령으로 다시 실행하여 실제 결과를 기록하세요. 완료 전에는 성공했다고 기록하지 않습니다.\n',
'Quotation_KEKOREA/README_CONTRACTS.md': '\n## 2026-11-06 commission payment wording compatibility\n\nThe default 7-calendar-day English payment clause prints `seven (7) calendar days` (D+7) to preserve the existing legal wording and regression assertion. A user-confirmed alternative number of days continues to print its actual numeric value. This is a presentation correction, not a change to the commercial payment policy or legal review requirements. Full regression results must be added after execution.\n',
'Quotation_KEKOREA/Team/README.md': '\n## 2026-11-06 회귀 테스트 보완\n\n상품 주석 확인 미완료 시 PO/PI PDF 및 Excel 생성 버튼을 차단하도록 연결했습니다. 실제 거래가격·가격근거·상품 원문은 수정하지 않습니다. 투자/무역 커미션 계약의 기본 7일 영문 문구는 `seven (7) calendar days`를 사용하며, 사용자 지정 기한은 그대로 유지합니다. `test_product_matching_ui.py`, `test_commission_policy.py` 및 전체 테스트 재실행 결과를 별도로 기록해야 합니다.\n',
'Quotation_KEKOREA/Presentation/README.md': '\n## 2026-11-06 시연 전 추가 확인\n\n상품명에 추가 설명이 붙어 검토 체크가 필요한 경우, 체크 전에는 PDF/Excel 버튼이 비활성화되고 사용자 확인 후 생성이 허용되는지 확인합니다. 계약 기본 커미션 지급기한 D+7의 영문 표기 일관성도 검증 대상입니다. 수정 코드는 테스트 및 실제 배포 확인 이전에는 운영 적용 완료로 소개하지 않습니다.\n',
}
for rel, block in notes.items():
    path = root / rel
    if not path.exists():
        raise SystemExit(f'Missing documentation {rel}; stopping before editing.')
    s = path.read_text(encoding='utf-8')
    if block.strip() not in s:
        changes.append((path,s.rstrip() + '\n' + block))
for path,data in changes:
    path.write_text(data,encoding='utf-8')
print(f'Updated {len(changes)} files. Existing tests are unchanged.')
print('Run: uv run --with-requirements .\\Quotation_KEKOREA\\requirements.txt python -m unittest discover -s .\\Quotation_KEKOREA\\tests -v')
