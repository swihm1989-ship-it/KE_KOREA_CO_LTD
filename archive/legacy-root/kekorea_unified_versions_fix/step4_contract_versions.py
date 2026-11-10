"""Apply the final copy/translation UI migration to the staged repository."""
from pathlib import Path
import ast

root=Path.cwd()
p=root/'Quotation_KEKOREA/contracts/ui.py'
s=p.read_text(encoding='utf-8')
if 'from Quotation_KEKOREA.contracts.contract_versions import copy_contract, translate_contract, localized_term_label' not in s:
    anchor='from Quotation_KEKOREA.contracts.exports import export_contract'
    if s.count(anchor)!=1:
        raise SystemExit('ui.py import anchor changed; no patch applied')
    s=s.replace(anchor,anchor+'\nfrom Quotation_KEKOREA.contracts.contract_versions import copy_contract, translate_contract, localized_term_label',1)
# English contract versions show English field labels in BOX 2, while
# retaining the existing Korean labels in Korean and existing internal keys.
row_marker="        rows.append({'key': key, '항목': label, 'value': value,"
if row_marker in s:
    s=s.replace(row_marker,
        "        label = localized_term_label(key, snapshot.get('language', 'ko'), label)\n"+row_marker,1)
# Dynamic editable column labels and sections for the chosen contract language.
s=s.replace('st.markdown("#### 거래금액·수수료·지급·기간·법률 및 기타 조건")',
            'st.markdown("#### Commercial terms, payment, term and law" if snapshot.get("language") == "en" else "#### 거래금액·수수료·지급·기간·법률 및 기타 조건")')
s=s.replace('st.markdown("#### 당사자 및 역할")',
            'st.markdown("#### Contract parties and roles" if snapshot.get("language") == "en" else "#### 당사자 및 역할")')
s=s.replace('st.column_config.TextColumn("조건 항목", disabled=True)',
            'st.column_config.TextColumn("Term" if snapshot.get("language") == "en" else "조건 항목", disabled=True)')
s=s.replace('st.column_config.TextColumn("값")',
            'st.column_config.TextColumn("Value" if snapshot.get("language") == "en" else "값")')
s=s.replace('st.column_config.TextColumn("단위")',
            'st.column_config.TextColumn("Unit" if snapshot.get("language") == "en" else "단위")')
s=s.replace('st.column_config.TextColumn("통화")',
            'st.column_config.TextColumn("Currency" if snapshot.get("language") == "en" else "통화")')
s=s.replace('st.column_config.TextColumn("내부 키", disabled=True)',
            'st.column_config.TextColumn("Internal key" if snapshot.get("language") == "en" else "내부 키", disabled=True)')
s=s.replace('st.column_config.TextColumn("법인명")',
            'st.column_config.TextColumn("Legal name" if snapshot.get("language") == "en" else "법인명")')
s=s.replace('st.column_config.TextColumn("국가")',
            'st.column_config.TextColumn("Country" if snapshot.get("language") == "en" else "국가")')
s=s.replace('st.column_config.TextColumn("주소")',
            'st.column_config.TextColumn("Address" if snapshot.get("language") == "en" else "주소")')
s=s.replace('st.column_config.TextColumn("대표/서명권자")',
            'st.column_config.TextColumn("Representative / signatory" if snapshot.get("language") == "en" else "대표/서명권자")')
s=s.replace('st.column_config.TextColumn("역할 (쉼표 구분)")',
            'st.column_config.TextColumn("Roles (comma-separated)" if snapshot.get("language") == "en" else "역할 (쉼표 구분)")')
start=s.find('    with st.expander("저장·복사·언어 버전 관리", expanded=False):')
if start<0:
    raise SystemExit('UI menu anchor changed; no patch applied')
# Menu is the final section of render_contract_page in current repo. Require
# matching known old content to avoid overwriting unrelated UI.
section=s[start:]
if 'copied["clauses"] = []' not in section and 'copy_contract(snapshot)' not in section:
    raise SystemExit('Unknown UI copy menu implementation; no patch applied')
if section.count('st.rerun()')<2:
    raise SystemExit('Unexpected UI menu structure; no patch applied')
replacement='''    with st.expander("저장·복사·언어 버전 관리", expanded=False):
        st.markdown("### 계약서 복사와 언어 버전")
        st.caption("복사는 현재 저장된 최신 revision의 조건과 조항을 그대로 사용합니다. "
                   "언어 버전은 번역 후 새 계약과 BOX 3 미리보기를 바로 만듭니다. 원본 계약은 변경하지 않습니다.")
        copy_col, language_col = st.columns(2)
        if copy_col.button("현재 계약 조건과 본문 그대로 새 계약으로 복사",
                           key=f"contract_copy_{active_id}"):
            try:
                copied = copy_contract(snapshot)
                _new_contract(repo, f"{snapshot.get('title', 'Contract')} (copy)",
                              snapshot['contract_type'], snapshot['language'], copied)
                st.rerun()
            except (ValueError, ContractRepositoryError) as exc:
                st.error(str(exc))
        new_language = "en" if snapshot["language"] == "ko" else "ko"
        st.caption("언어 변환 시 계약 조항과 BOX 2의 설명형 조건도 번역합니다. "
                   "금액·수량·법인명·품목코드·거래조건은 변경하지 않습니다.")
        translation_consent = language_col.checkbox(
            "계약 본문 및 조건의 AI 번역 전송 동의",
            key=f"contract_translate_consent_{active_id}")
        if language_col.button(f"{'English' if new_language == 'en' else '한국어'} 버전 새로 만들기",
                               disabled=not translation_consent,
                               key=f"contract_language_version_{active_id}"):
            try:
                if not snapshot.get('clauses'):
                    raise ValueError("먼저 기존 계약서의 BOX 3 본문을 저장해 주세요.")
                with st.spinner("계약 조항과 조건을 번역하고 내용 일치 여부를 검사합니다..."):
                    translated = translate_contract(snapshot, new_language, env=env)
                _new_contract(repo, translated.get('title') or snapshot.get('title','Contract'),
                              snapshot['contract_type'], new_language, translated)
                st.rerun()
            except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                st.error("번역본을 만들지 않았습니다. 원본은 그대로 유지됩니다: " + str(exc))
'''
s=s[:start]+replacement
ast.parse(s)
p.write_text(s,encoding='utf-8')
print('Copy and translation menu patched successfully')
