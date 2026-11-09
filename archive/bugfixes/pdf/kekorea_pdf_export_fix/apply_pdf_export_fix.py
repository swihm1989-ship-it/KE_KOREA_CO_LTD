"""Apply narrow contract export UI fix. Run from repository root.
Never alters export validation, PDF renderers, business rules, or document modules.
"""
from pathlib import Path
from datetime import datetime
import shutil

ROOT=Path.cwd()
UI=ROOT/'Quotation_KEKOREA/contracts/ui.py'
BEFORE='''                        _persist_contract_outputs(repo, snapshot, outputs, mode)
                        st.session_state[f"contract_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}"] = outputs[extension]
                        st.success("현재 revision의 파일을 비공개 저장했습니다.")
                    except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                        st.error(f"파일 생성/저장에 실패했습니다. {exc}")
                output = st.session_state.get(f"contract_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
                if output and not (mode == 'final' and issues):
                    st.download_button(f"{title} {extension.upper()} 다운로드", data=output['content'],
                                       file_name=output['filename'], mime=_contract_mime(extension),
                                       key=f"contract_download_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
    current_exports = [item for item in repo.list_exports(snapshot['contract_id'])
                       if item.get('revision') == snapshot['revision']]
'''
AFTER='''                        # Render first, then save privately. Do not conflate a valid PDF
                        # with a failed Supabase upload or export-record write.
                        local_key = f"contract_unsaved_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}"
                        saved_key = f"contract_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}"
                        try:
                            _persist_contract_outputs(repo, snapshot, outputs, mode)
                        except ContractRepositoryError as storage_exc:
                            # _persist_contract_outputs already performs its normal
                            # partial-upload rollback. Keep bytes only in this session,
                            # not in the DB or a public location.
                            st.session_state[local_key] = outputs[extension]
                            st.session_state.pop(saved_key, None)
                            st.warning("파일은 생성됐지만 비공개 저장소 기록에 실패했습니다. "
                                       "아래 '직접 다운로드'로 받을 수 있습니다. "
                                       f"서버 저장 실패 원인: {storage_exc}")
                        else:
                            st.session_state.pop(local_key, None)
                            st.session_state[saved_key] = outputs[extension]
                            st.success("현재 revision의 파일을 비공개 저장했습니다.")
                    except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                        st.error(f"파일 생성 단계에서 실패했습니다. {exc}")
                output = st.session_state.get(f"contract_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
                if output and not (mode == 'final' and issues):
                    st.download_button(f"{title} {extension.upper()} 다운로드", data=output['content'],
                                       file_name=output['filename'], mime=_contract_mime(extension),
                                       key=f"contract_download_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
                local_output = st.session_state.get(
                    f"contract_unsaved_output_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
                if local_output and not (mode == 'final' and issues):
                    st.download_button(f"{title} {extension.upper()} 직접 다운로드 (서버 미저장)",
                                       data=local_output['content'], file_name=local_output['filename'],
                                       mime=_contract_mime(extension),
                                       key=f"contract_local_download_{mode}_{snapshot['contract_id']}_{snapshot['revision']}_{extension}")
    try:
        current_exports = [item for item in repo.list_exports(snapshot['contract_id'])
                           if item.get('revision') == snapshot['revision']]
    except ContractRepositoryError as exc:
        st.caption(f"비공개 출력 기록을 조회하지 못했습니다. 서버 저장 상태를 확인해 주세요: {exc}")
        current_exports = []
'''
DOCS={
'README.md': '\n### 계약서 PDF/Word 출력 진단\nPDF/DOCX를 메모리에서 만든 후 비공개 저장소 저장이 실패한 경우, 사용자 세션에만 파일을 보유하여 직접 다운로드할 수 있다. FINAL의 기존 필수조건 검증은 우회하지 않으며, 서버 미저장 파일은 출력 기록으로 표시하지 않는다.\n',
'Quotation_KEKOREA/README.md': '\n### 계약서 PDF/Word 저장 실패 구분\n계약서 파일 렌더링이 성공했지만 Supabase 비공개 저장 또는 export 기록 저장이 실패하면, 기존 부분 업로드 정리를 유지하면서 현재 브라우저 세션에 한해 직접 다운로드 버튼을 제공한다. 파일 생성 실패와 서버 저장 실패를 구분해 안내한다. 최종 계약서는 기존 `validate_rules(..., for_export=True)` 조건을 통과해야 한다.\n',
'Quotation_KEKOREA/README_CONTRACTS.md': '\n### PDF/DOCX 렌더링과 비공개 저장 실패 처리\n렌더링 성공/비공개 파일 업로드 성공/출력 이력 저장 성공을 구별한다. 렌더링은 성공했으나 `ContractRepositoryError`가 발생한 경우 기존 롤백 후 세션 내 **직접 다운로드 (서버 미저장)** 링크를 제공한다. 저장소에 없는 결과를 저장 성공이라고 주장하지 않는다. 렌더링 자체가 실패하면 다운로드 버튼을 만들지 않는다. FINAL 검증이나 계약조건 상태를 변경하지 않는다.\n',
'Quotation_KEKOREA/Team/README.md': '\n### 계약서 출력 장애 시\nDRAFT/FINAL 모두 렌더링 단계와 비공개 저장 단계를 구분한다. 저장 실패만 발생했으면 브라우저 세션의 직접 다운로드로 확인하고, Supabase Storage 버킷 `kekorea-contracts` 및 exports 테이블 권한/설정을 점검한다. FINAL 필수검증은 유지한다.\n',
'Quotation_KEKOREA/Presentation/README.md': '\n### 계약서 출력 예외 시연\nPDF 또는 Word는 렌더링을 우선 수행하고 서버 저장 오류가 발생하면 임시 세션 직접 다운로드를 표시한다. 서버 저장/감사 로그가 성공한 것처럼 보이지 않으며 FINAL 검증을 우회하지 않는다. 실제 운영 Storage 권한 및 배포 테스트는 별도 확인 대상이다.\n',
}
TEST=ROOT/'Quotation_KEKOREA/tests/test_contract_export_storage_fallback.py'
TEST_BODY='''"""Storage failure must not discard an already-rendered contract file."""
import unittest
from unittest.mock import patch

from Quotation_KEKOREA.tests.test_contract_three_box_ui import ThreeBoxUiTests
from Quotation_KEKOREA.contracts.repository import ContractRepositoryError


class ExportStorageFallbackTests(ThreeBoxUiTests):
    def test_draft_pdf_survives_private_storage_failure_in_session(self):
        self.run_app()
        with patch.object(self.repo, 'save_export', side_effect=ContractRepositoryError('simulated DB failure')):
            self.button('검토용 초안 PDF').click()
            self.run_app()
        self.assertEqual(self.repo.exports, [])
        self.assertEqual(self.repo.files, {})
        self.assertNotIn('contract_output_draft_sample_1_pdf', self.at.session_state)
        recovered = self.at.session_state['contract_unsaved_output_draft_sample_1_pdf']
        self.assertTrue(recovered['content'].startswith(b'%PDF-'))

    def test_pdf_renderer_failure_does_not_offer_local_file(self):
        self.run_app()
        with patch('Quotation_KEKOREA.contracts.ui.export_draft', side_effect=ValueError('simulated render error')):
            self.button('검토용 초안 PDF').click()
            self.run_app()
        self.assertNotIn('contract_unsaved_output_draft_sample_1_pdf', self.at.session_state)
        self.assertFalse(self.repo.exports)

    def test_final_still_blocked_with_missing_required_terms(self):
        self.run_app()
        self.assertTrue(self.button('최종 계약서 PDF').disabled)
        self.assertNotIn('contract_unsaved_output_final_sample_1_pdf', self.at.session_state)


if __name__ == '__main__':
    unittest.main()
'''

def main():
    if not UI.exists():
        raise SystemExit('ERROR: run inside KE_KOREA_CO_LTD repository root')
    s=UI.read_text(encoding='utf-8')
    if AFTER in s:
        raise SystemExit('ALREADY APPLIED: no files changed')
    if s.count(BEFORE)!=1:
        raise SystemExit('STOP: export code is not the verified version. Nothing changed.')
    if TEST.exists():
        raise SystemExit('STOP: test path already exists; review changes before continuing')
    for path in DOCS:
        if not (ROOT/path).exists():
            raise SystemExit(f'STOP: missing README {path}')
    backup=ROOT/'kekorea_pdf_export_fix_backup'/datetime.now().strftime('%Y%m%d_%H%M%S')
    for path in [UI,*[ROOT/p for p in DOCS]]:
        destination=backup/path.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,destination)
    UI.write_text(s.replace(BEFORE,AFTER),encoding='utf-8')
    for relative,append in DOCS.items():
        target=ROOT/relative
        target.write_text(target.read_text(encoding='utf-8').rstrip()+"\n"+append,encoding='utf-8')
    TEST.parent.mkdir(parents=True, exist_ok=True)
    TEST.write_text(TEST_BODY,encoding='utf-8')
    print(f'Applied safely. Backup: {backup}')
    print('Only contract UI, one test, and five READMEs changed.')
    print('Run entire test suite before commit or deploy.')

if __name__=='__main__':main()
