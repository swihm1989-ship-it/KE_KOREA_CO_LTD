KE KOREA - 수수료 지급조건 편집 패치

적용 파일은 두 개뿐입니다.
- Quotation_KEKOREA/contracts/commission_policy.py
- Quotation_KEKOREA/contracts/ui.py

사용법 (VS Code PowerShell / KE_KOREA_CO_LTD 폴더):
  python .\contract_payment_editor_fix\apply_contract_payment_editor.py
  Copy-Item .\contract_payment_editor_fix\test_contract_payment_editor.py .\Quotation_KEKOREA\tests\
  uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -p "test_contract*.py" -v

실제 회사계좌는 이 화면에서 직접 입력하거나 인증하지 않습니다.
지급자 국가 및 연체이율 등 법적 적용 가능성은 계약 체결 전에 확인해야 합니다.
테스트가 성공한 다음에만 위 두 파일과 신규 테스트를 GitHub에 반영하세요.
