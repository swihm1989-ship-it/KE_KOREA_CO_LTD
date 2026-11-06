# KE KOREA 계약서 검토 화면 간소화 적용

## 변경되는 범위

- `contracts/ui.py`에서 문서 다운로드를 먼저 표시하고, 긴 `서명 전 검토` 목록을 다운로드 **아래쪽**의 `고급 검토 기록 · 확정 근거 확인 (선택)`으로 이동합니다.
- 기존 AI 쟁점 확인/저장 버튼은 삭제하지 않습니다. 다만 기본 화면에서 직접 보이지 않습니다.
- DRAFT PDF/DOCX는 이미 미확정 정보를 표시하며 생성하도록 되어 있습니다. 이 패치는 FINAL 차단을 해제하지 **않습니다**.
- `rules.py`, `draft_exports.py`, `exports.py`, ECLADO 및 PO/PI/CI/PL은 변경하지 않습니다.
- README 5개를 수정합니다.

## 적용

이 ZIP을 프로젝트 최상위로 풀어 아래 명령을 실행합니다.

```powershell
python .\kekorea_export_review_cleanup\apply_review_cleanup.py
```

스크립트는 이전 소스가 정확히 일치하지 않을 경우 변경 없이 중단합니다. 복사된 백업은 프로젝트의 `kekorea_export_review_cleanup_backup`에 저장됩니다. 이 백업 폴더는 커밋하지 마세요.

## 테스트

```powershell
uv run --with-requirements .\Quotation_KEKOREA\requirements.txt python -m unittest discover -s .\Quotation_KEKOREA\tests -v
git diff --check
python scripts/check_readme_sync.py
```

## 기대 동작

1. `문서 다운로드`가 `고급 검토 기록`보다 먼저 보입니다.
2. 최종 확인할 항목이 있으면 `FINAL` 버튼은 비활성화됩니다.
3. `검토용 초안 PDF` 또는 `검토용 초안 DOCX`를 선택해 **파일 생성**을 진행할 수 있습니다. 생성 후 **다운로드 버튼**을 눌러 실제 파일을 내려받습니다.
4. 기존 계약서 문구가 변경되는 것은 아닙니다.
5. 저장소, API, 비공개 파일 버킷 오류가 있으면 DRAFT 저장도 실패할 수 있으므로, 이 경우 실제 오류 문구를 확인해야 합니다.

## Git 주의

`git add .` 대신 변경된 UI 코드와 README 5개만 추가하세요. 미리보기 패치/백업 폴더를 커밋하지 마세요. 모든 테스트가 통과한 후에만 커밋/푸시하세요.
