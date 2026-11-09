# 과거 수정본 및 백업 보관함

현재 실행 코드는 `../Quotation_KEKOREA/`, 공식 회귀 테스트는 `../Quotation_KEKOREA/tests/`에 있습니다. 이 폴더는 과거 오류 수정 패키지와 백업을 찾기 위한 기록 보관함입니다.

## 기능별 오류 수정본

- [화면·문장 정렬·메모 UI](bugfixes/ui/)
- [PDF·내보내기](bugfixes/pdf/)
- [언어 처리](bugfixes/language/)
- [거래조건·지급조건](bugfixes/conditions/)
- [참고자료·라이브러리·RAG](bugfixes/references/)
- [계약 위험 검토](bugfixes/risk_review/)
- [계약·무역 문서 흐름](bugfixes/workflow/)
- [OCR·JSON 요청](bugfixes/ocr/)
- [테스트 오류 수정](bugfixes/testing/)
- [문서·README 동기화](bugfixes/documentation/)

## 보관 원칙

- 패키지의 보조 테스트·수정 코드·내장 백업은 서로의 경로 관계를 보존하기 위해 함께 보관합니다. 공식 테스트 실행 대상은 `Quotation_KEKOREA/tests`입니다.
- [독립 백업](backups/)에는 이전 소스와 문서 복사본을 보존합니다.
- [테스트 로그](../logs/tests/)는 실행 결과 기록입니다.
- 과거 적용 스크립트는 현재 소스에 재실행하지 마세요. 일부는 이전 폴더 깊이 또는 당시 코드 형태를 가정합니다. 재사용 시 루트 탐색·대상 코드 버전을 먼저 검토해야 합니다.
- 파일 내용은 수정하지 않았습니다. [이동 명세](move_manifest_2026-11-09.json)에 이전 경로·새 경로·파일별 SHA-256을 기록했습니다.

## 이전 경로 → 현재 경로

| 이전 루트 경로 | 현재 위치 |
| --- | --- |
| `contract_ui_simplification` | [archive/bugfixes/ui/contract_ui_simplification](bugfixes/ui/contract_ui_simplification) |
| `kekorea_first_option_fix` | [archive/bugfixes/ui/kekorea_first_option_fix](bugfixes/ui/kekorea_first_option_fix) |
| `kekorea_full_sentence_patch` | [archive/bugfixes/ui/kekorea_full_sentence_patch](bugfixes/ui/kekorea_full_sentence_patch) |
| `kekorea_inline_ui_patch` | [archive/bugfixes/ui/kekorea_inline_ui_patch](bugfixes/ui/kekorea_inline_ui_patch) |
| `kekorea_sentence_alignment_fix` | [archive/bugfixes/ui/kekorea_sentence_alignment_fix](bugfixes/ui/kekorea_sentence_alignment_fix) |
| `kekorea_sentence_left_edge_fix` | [archive/bugfixes/ui/kekorea_sentence_left_edge_fix](bugfixes/ui/kekorea_sentence_left_edge_fix) |
| `kekorea_pdf_export_fix` | [archive/bugfixes/pdf/kekorea_pdf_export_fix](bugfixes/pdf/kekorea_pdf_export_fix) |
| `kekorea_export_review_cleanup` | [archive/bugfixes/pdf/kekorea_export_review_cleanup](bugfixes/pdf/kekorea_export_review_cleanup) |
| `contract_language_fix_v2` | [archive/bugfixes/language/contract_language_fix_v2](bugfixes/language/contract_language_fix_v2) |
| `apply_contract_language.py` | [archive/bugfixes/language/apply_contract_language.py](bugfixes/language/apply_contract_language.py) |
| `contract_payment_editor_fix` | [archive/bugfixes/conditions/contract_payment_editor_fix](bugfixes/conditions/contract_payment_editor_fix) |
| `kekorea_clause_terms_fix` | [archive/bugfixes/conditions/kekorea_clause_terms_fix](bugfixes/conditions/kekorea_clause_terms_fix) |
| `contract_rag_review_patch` | [archive/bugfixes/references/contract_rag_review_patch](bugfixes/references/contract_rag_review_patch) |
| `kekorea_shared_library_bridge` | [archive/bugfixes/references/kekorea_shared_library_bridge](bugfixes/references/kekorea_shared_library_bridge) |
| `kekorea_risk_review_v2` | [archive/bugfixes/risk_review/kekorea_risk_review_v2](bugfixes/risk_review/kekorea_risk_review_v2) |
| `kekorea_risk_preview_visibility_fix` | [archive/bugfixes/risk_review/kekorea_risk_preview_visibility_fix](bugfixes/risk_review/kekorea_risk_preview_visibility_fix) |
| `contract_workflow_fix` | [archive/bugfixes/workflow/contract_workflow_fix](bugfixes/workflow/contract_workflow_fix) |
| `ci_draft_regression_fix` | [archive/bugfixes/workflow/ci_draft_regression_fix](bugfixes/workflow/ci_draft_regression_fix) |
| `kekorea_note_revision_fix` | [archive/bugfixes/workflow/kekorea_note_revision_fix](bugfixes/workflow/kekorea_note_revision_fix) |
| `kekorea_unified_final_fix` | [archive/bugfixes/workflow/kekorea_unified_final_fix](bugfixes/workflow/kekorea_unified_final_fix) |
| `kekorea_ocr_json_fix` | [archive/bugfixes/ocr/kekorea_ocr_json_fix](bugfixes/ocr/kekorea_ocr_json_fix) |
| `kekorea_clause_terms_test_fix` | [archive/bugfixes/testing/kekorea_clause_terms_test_fix](bugfixes/testing/kekorea_clause_terms_test_fix) |
| `kekorea_risk_review_test_fix` | [archive/bugfixes/testing/kekorea_risk_review_test_fix](bugfixes/testing/kekorea_risk_review_test_fix) |
| `kekorea_test_fix` | [archive/bugfixes/testing/kekorea_test_fix](bugfixes/testing/kekorea_test_fix) |
| `fix_contract_library_test.py` | [archive/bugfixes/testing/fix_contract_library_test.py](bugfixes/testing/fix_contract_library_test.py) |
| `taste_contract_readme_update` | [archive/bugfixes/documentation/taste_contract_readme_update](bugfixes/documentation/taste_contract_readme_update) |
| `.local_contract_ui_backup_20261106_163707` | [archive/backups/.local_contract_ui_backup_20261106_163707](backups/.local_contract_ui_backup_20261106_163707) |
| `clause_terms_fix_backup_20261109_105838` | [archive/backups/clause_terms_fix_backup_20261109_105838](backups/clause_terms_fix_backup_20261109_105838) |
| `kekorea_alignment_backup_20261109_103434` | [archive/backups/kekorea_alignment_backup_20261109_103434](backups/kekorea_alignment_backup_20261109_103434) |
| `kekorea_export_review_cleanup_backup` | [archive/backups/kekorea_export_review_cleanup_backup](backups/kekorea_export_review_cleanup_backup) |
| `kekorea_pdf_export_fix_backup` | [archive/backups/kekorea_pdf_export_fix_backup](backups/kekorea_pdf_export_fix_backup) |
| `kekorea_sentence_left_edge_fix_backup_20261109_105239` | [archive/backups/kekorea_sentence_left_edge_fix_backup_20261109_105239](backups/kekorea_sentence_left_edge_fix_backup_20261109_105239) |
| `test_results.txt` | [logs/tests/test_results.txt](../logs/tests/test_results.txt) |
| `contract_test_full.log` | [logs/tests/contract_test_full.log](../logs/tests/contract_test_full.log) |
