"""Conservative local patch. Run from KE_KOREA_CO_LTD root.

Refuses unfamiliar source shapes. Backups are written outside Git source into patch folder.
"""
from pathlib import Path
from datetime import datetime
import shutil
import py_compile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
APP=ROOT/'Quotation_KEKOREA'
UI=APP/'contracts'/'ui.py'
FILES=[ROOT/'README.md',APP/'README.md',APP/'README_CONTRACTS.md',
       APP/'Team'/'README.md',APP/'Presentation'/'README.md']
TOKEN='## 2026-11-06 AI 위험 검토 페이지·추천안 확장'


def main():
    if not UI.is_file():
        raise SystemExit('ERROR: Place kekorea_risk_review_v2 inside the KE_KOREA_CO_LTD repository root.')
    original=UI.read_text(encoding='utf-8')
    if TOKEN in (APP/'README_CONTRACTS.md').read_text(encoding='utf-8'):
        raise SystemExit('Already applied; refusing duplicate patch.')
    if "from Quotation_KEKOREA.contracts.risk_review_ui import render_risk_review" in original:
        raise SystemExit('Already modified; refusing duplicate patch.')
    marker='            # Contract RAG risk-review panel (read-only; user approval required)'
    next_marker='            with st.expander("Revision 기록 및 복원", expanded=False):'
    if original.count(marker)!=1 or original.count(next_marker)!=1:
        raise SystemExit('ERROR: Unknown contract UI version. No changes made.')
    start=original.index(marker)
    end=original.index(next_marker,start)
    if 'review_contract(snapshot' not in original[start:end]:
        raise SystemExit('ERROR: Expected old risk panel absent. No changes made.')
    changed=original[:start]+('            render_risk_review(repo, snapshot, state_key, env)\n')+original[end:]
    anchor='from Quotation_KEKOREA.contracts.workspace import collect_notes, propose_notes_revision\n'
    if changed.count(anchor)!=1:
        raise SystemExit('ERROR: Import anchor not found.')
    changed=changed.replace(anchor,anchor+'from Quotation_KEKOREA.contracts.risk_review_ui import render_risk_review\n',1)
    segment_start=changed.index('def _render_draft(')
    segment_end=changed.index('\ndef _note_row(',segment_start)
    part=changed[segment_start:segment_end]
    note_anchor="                    sentence_id = sentence['id']\n"
    if part.count(note_anchor)!=1 or part.count("st.button(sentence['text'],")!=1:
        raise SystemExit('ERROR: Unknown sentence preview layout. No changes made.')
    addition=("                    preview = st.session_state.get(f'contract_risk_preview_{contract_id}') or {}\n"
              "                    preview_texts = preview.get('sentences', {}) if preview.get('revision') == revision else {}\n"
              "                    displayed_text = preview_texts.get(sentence_id, sentence['text'])\n")
    part=part.replace(note_anchor,note_anchor+addition,1)
    part=part.replace("st.button(sentence['text'],",'st.button(displayed_text,',1)
    changed=changed[:segment_start]+part+changed[segment_end:]
    if changed.count('render_risk_review(repo, snapshot, state_key, env)')!=1:
        raise SystemExit('ERROR: Unexpected duplicate risk panel')
    targets={UI:changed}
    for name in ('risk_review_workspace.py','risk_review_ui.py'):
        target=APP/'contracts'/name
        if target.exists():
            raise SystemExit(f'ERROR: {target} already exists; not overwriting.')
        targets[target]=(HERE/name).read_text(encoding='utf-8')
    target_test=APP/'tests'/'test_contract_risk_review_v2.py'
    if target_test.exists():
        raise SystemExit('ERROR: Risk-review test file already exists.')
    targets[target_test]=(HERE/'test_contract_risk_review_v2.py').read_text(encoding='utf-8')
    notes={
      FILES[0]: '계약서 BOX 3의 AI 위험 검토는 전체 조항을 검토하고 항목을 5건씩 페이지에 표시한다. 선택한 위험에 대해 균형형·권리 보호형·보수적 협의형 추천 3안을 생성하며 가변값과 문장 전체를 직접 편집할 수 있다. 추천 적용은 미리보기만 갱신하고 기존 비교·승인 후 새 revision에 저장한다.',
      FILES[1]: '계약서 위험 검토 개선: 전체 조항을 10문장 이하 묶음으로 기존 출처 검증 위험 검토에 전달하고 최종 결과는 5건씩 페이지 표시한다. 선택한 위험에 대해 모델에서 추천 문장 3개를 생성한다. 숫자·법인명은 검증된 가변 템플릿으로만 변경할 수 있다. 사용자가 선택한 문장은 BOX 3에서 즉시 미리보기로 표시하되 기존 revision/FINAL 검증은 유지한다.',
      FILES[2]: 'contracts/risk_review_workspace.py는 기존 contracts/review.py의 검증을 유지한 채 전체 조항을 분할해 위험 결과를 모으고 페이지당 5개로 보여준다. 추천안은 선택 위험에서 사용자 요청 시 3개 생성되며, 변수 이름·값은 모델 결과를 검증한 뒤 편집한다. contracts/risk_review_ui.py는 추천 3개 중 선택, 가변정보 수정, 문장 편집, 수정 미리보기 및 기존 proposal 승인 경로를 제공한다. 적용은 DB에 즉시 저장하지 않으며, 이미 저장된 메모·커미션 지급정책·FINAL 출력을 자동 변경하지 않는다. 기존 위험 검토 함수의 단일 호출 5건 제한과 전체 검토 묶음 방식은 구별된다.',
      FILES[3]: '팀 시연: BOX 3 > AI 핵심 위험 검토 > 전체 위험 검토 > 1/2/3 페이지 이동 > 항목 선택 > 추천안 3개 생성 > 가변값·문장 직접 편집 > 추천 문장 적용 > BOX 3 미리보기 확인 > 선택한 수정안 비교·승인. 관련 코드는 risk_review_workspace.py 및 risk_review_ui.py. 기존 PO/PI/CI/PL·ECLADO 및 법률 검증 엔진은 변경하지 않았다.',
      FILES[4]: '위험 검토 시연: 기존 5건 고정에서 전체 조항 분할 검토와 페이지당 5건으로 확장한다. 선택 위험별 AI 추천안 3개, 숫자·법인명 편집, BOX 3 즉시 미리보기, 승인 후 revision 저장을 보여준다. AI 문구는 법률 자문이나 통계적으로 확인된 글로벌 표준이 아니다. 브라우저 시각 검수와 운영 환경 확인은 별도다.'
    }
    for file,doc in notes.items():
        if not file.exists():
            raise SystemExit(f'ERROR: README not found: {file}')
        original_doc=file.read_text(encoding='utf-8')
        # Explicitly retire misleading current-purpose wording, but preserve historical logs.
        targets[file]=original_doc.rstrip()+'\n\n'+TOKEN+'\n\n'+doc+'\n'
    # Validate new code and new test before changing anything.
    for code in ('risk_review_workspace.py','risk_review_ui.py','test_contract_risk_review_v2.py'):
        compile((HERE/code).read_text(encoding='utf-8'),code,'exec')
    compile(changed,str(UI),'exec')
    backup=HERE/('backup_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=True)
    for file in targets:
        if file.exists():
            saved=backup/file.relative_to(ROOT)
            saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(file,saved)
    try:
        for file,content in targets.items():
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(content,encoding='utf-8')
    except Exception:
        for file in targets:
            saved=backup/file.relative_to(ROOT)
            if saved.is_file():
                shutil.copy2(saved,file)
            elif file.exists():
                file.unlink()
        raise
    print('Applied: risk-review pagination / three options / variable editing / BOX 3 preview.')
    print('Backups:',backup)
    print('Edited code: contracts/ui.py; added risk_review_workspace.py, risk_review_ui.py, test_contract_risk_review_v2.py')
    print('Updated all 5 README files. Run all tests before commit or deployment.')


if __name__=='__main__':main()
