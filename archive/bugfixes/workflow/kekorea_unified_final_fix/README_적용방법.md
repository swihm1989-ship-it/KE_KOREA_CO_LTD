# KE KOREA · BOX 3 통합 최종 수정 패치

## 변경 범위

- 문장별 메모 → 이전·제외 메모 → AI 핵심 위험 검토 → Revision 기록/복원 → **최종 수정 요청** → 통합 수정안 비교·승인 → 문서 다운로드
- 위험 검토에서 선택한 문장만 있어도 `최종 수정 요청` 활성화 (메모 0개 가능)
- 메모가 있으면 BOX 1의 기존 외부 AI 전송 동의를 요구하고 한 번의 AI 요청으로 문장별 메모를 검토
- 메모와 위험 검토 수정 문구를 같은 revision에 합치되, **같은 문장에 두 수정이 겹치면 차단 및 조정 안내**
- 승인 전에 계약서 원본은 유지되며, 기존 `선택한 변경을 하나의 revision으로 적용` 버튼으로 저장 후 BOX 3 반영
- 계약서 검증/비공개 저장/DRAFT·FINAL/PDF/DOCX/지급 정책/ECLADO·PO·PI·CI·PL 수정 없음
- 다섯 README 함께 업데이트

## 적용

1. ZIP 압축을 풀어 프로젝트 최상위 폴더에 `kekorea_unified_final_fix` 디렉터리를 배치한다.
2. VS Code PowerShell에서 프로젝트 최상위로 이동 후 다음 명령 실행:

```powershell
python .\kekorea_unified_final_fix\apply_unified_final_fix.py
```

3. **중요:** 이미 진행 중인 다른 패치의 미커밋 변경이 있는 경우 원본을 덮어쓰지 않도록 적용 전 `git status --short`를 확인한다. 스크립트는 대상 코드 앵커가 바뀌면 아무것도 수정하지 않고 중단한다. 적용 전 원본 파일과 README는 패키지의 `backup_YYYYMMDD_HHMMSS`에 백업된다.

## 테스트

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest Quotation_KEKOREA.tests.test_contract_unified_final -v
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v
git diff --check
python scripts/check_readme_sync.py
```

## UI 확인

1. 저장된 계약서를 열어 BOX 3에서 위험 검토 추천 문장을 선택/적용한다.
2. 문장 메모가 **0개라도**, 수정 위험 문장이 1개 이상 있으면 하단 `최종 수정 요청`이 활성화되는지 본다.
3. 메모도 입력했다면 BOX 1 AI 전송 동의를 켜고, 충돌하지 않는 경우 하단 `최종 수정 요청`을 클릭한다.
4. 아래에 나타나는 비교를 확인한 뒤 `선택한 변경을 하나의 revision으로 적용`을 누른다.
5. BOX 3 문구가 새 revision에서 바뀌었는지 확인한다.
6. 기존 PDF/DOCX 다운로드 검증 규칙은 동일하다. FINAL 제한은 자동 해제하지 않는다.

테스트가 통과하기 전 GitHub에 푸시하거나 운영 배포하지 않는다.
