# 실행 로그

- `tests/`: 전체 테스트의 과거 실행 기록. 최신 성공 여부는 해당 로그의 실행 시각과 마지막 요약으로 확인합니다.
- 새 테스트 로그는 `logs/tests/`에 저장하세요. 터미널에서 진행 상태도 보려면 PowerShell에서 `2>&1 | Tee-Object -FilePath .\logs\tests\contract_test_full.log`를 사용합니다.
- 과거 실패 로그는 현재 코드의 실패를 의미하지 않습니다. 로그에는 비밀정보나 원본 거래 자료를 넣지 않습니다.
