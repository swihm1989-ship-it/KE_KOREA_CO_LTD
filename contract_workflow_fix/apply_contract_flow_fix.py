"""Apply a narrowly-scoped draft-first contract conversation fix. Run at repository root."""
from pathlib import Path
import ast

ROOT = Path.cwd()
UI = ROOT / 'Quotation_KEKOREA/contracts/ui.py'
SERVICE = ROOT / 'Quotation_KEKOREA/contracts/service.py'
HELPER = ROOT / 'Quotation_KEKOREA/contracts/flow.py'


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one original code block, found {count}. No files modified.')
    return text.replace(old, new, 1)


flow = '''"""Deterministic guardrails for the draft-first contract chat."""
import re


def wants_contract_draft(text):
    """Explicit user request to prepare a draft; never infer from prior messages."""
    text = str(text or '').strip()
    if re.search(r'(초안|계약서).{0,50}(작성|만들|생성|보여|써\s*줘|써\s*주세요)', text):
        return True
    if re.search(r'(작성|만들|생성).{0,30}(초안|계약서)', text):
        return True
    return bool(re.search(r'\\b(draft|generate|create|write)\\b.{0,60}\\b(contract|agreement|draft)\\b',
                          text, flags=re.IGNORECASE) or
                re.search(r'\\b(contract|agreement)\\b.{0,60}\\b(draft|generate|create|write)\\b',
                          text, flags=re.IGNORECASE))


def should_generate_draft(prompt, messages, *, has_clauses=False):
    """Draft on explicit request or after the first follow-up response."""
    return not has_clauses and (wants_contract_draft(prompt) or
                                sum(m.get('role') == 'user' for m in messages) >= 2)


def select_new_questions(questions, messages, *, limit=2):
    """No recurring interrogation: one round, max two focused questions.

    This affects conversational questions only; safety issues remain available
    in the review panel and required checks for final export remain unchanged.
    """
    if limit <= 0 or sum(m.get('role') == 'user' for m in messages) >= 2:
        return []
    previous = re.sub(r'[^0-9a-z가-힣]+', '', '\\n'.join(
        str(m.get('content') or '') for m in messages
        if m.get('role') == 'assistant').casefold())
    selected = []
    fingerprints = set()
    for raw in questions or []:
        question = str(raw or '').strip()
        normalized = re.sub(r'[^0-9a-z가-힣]+', '', question.casefold())
        if not normalized or normalized in previous or normalized in fingerprints:
            continue
        fingerprints.add(normalized)
        selected.append(question)
        if len(selected) >= max(0, limit):
            break
    return selected
'''

old_import = '''from Quotation_KEKOREA.contracts.service import (
    analyze_trade, conversation_response_language, extract_reference_page, generate_draft, language_conflict,
    propose_revision, propose_term_revision,
)
'''
new_import = old_import + '''from Quotation_KEKOREA.contracts.flow import should_generate_draft, select_new_questions
'''
old_process = '''            updated = apply_analysis(snapshot, analysis)
            updated['library_sources'] = library_result['sources']
            updated["reference_ids"] = sorted(set(
                updated.get("reference_ids", []) + selected_refs
            ))
            if snapshot.get("clauses"):
'''
new_process = '''            # First conversation response can ask up to two questions; after the
            # user's next message generate the draft instead of asking again.
            make_draft = should_generate_draft(
                prompt, prior_messages, has_clauses=bool(snapshot.get("clauses")))
            analysis["questions"] = ([] if make_draft else
                                     select_new_questions(analysis.get("questions", []), prior_messages))
            updated = apply_analysis(snapshot, analysis)
            updated['library_sources'] = library_result['sources']
            updated["reference_ids"] = sorted(set(
                updated.get("reference_ids", []) + selected_refs
            ))
            made_draft = False
            if make_draft:
                preferred = [clause for clause in repo.list_preferred_clauses()
                             if clause.get("active")
                             and updated["contract_type"] in clause.get("contract_types", [])
                             and clause.get("language") == updated["language"]]
                with st.spinner("확인되지 않은 항목을 표시하고 계약서 초안을 작성합니다..."):
                    updated = generate_draft(
                        updated, preferred, env=env, reference_context=selected_context,
                        transaction_messages=prior_messages)
                updated["library_sources"] = library_result["sources"]
                made_draft = True
            if snapshot.get("clauses"):
'''
old_response = '''            response_language = conversation_response_language(prompt)
            if response_language == "en":
'''
new_response = '''            response_language = conversation_response_language(prompt)
            if made_draft:
                response = ("Draft generated. Review the contract below and click individual sentences to request edits."
                            if response_language == "en" else
                            "계약서 초안을 작성했습니다. 아래 본문을 검토하고 수정할 문장을 클릭해 명령해 주세요. "
                            "미확정 사항은 검토 항목으로 남겨두었습니다.")
                repo.add_message(snapshot["contract_id"], "assistant", response)
                st.rerun()
            if response_language == "en":
'''
old_questions = '''    questions = snapshot.get("questions", [])
    if questions:
        with st.expander("AI 확인 질문", expanded=True):
'''
new_questions = '''    questions = snapshot.get("questions", [])
    if questions and not snapshot.get("clauses"):
        with st.expander("초안 작성 전 확인할 핵심 질문 (선택)", expanded=False):
'''
old_hint = '''    st.caption("이전 대화는 채팅창에서 확인할 수 있습니다. 메시지를 입력하면 조건 분석이 진행되며, 입력 자료와 선택한 참고 문구는 동의 후 전송됩니다.")
'''
new_hint = '''    st.caption("원하는 계약조건을 입력한 뒤 '계약서 초안을 작성해줘'라고 요청하세요. "
               "반복 질문 대신 초안을 먼저 만들고, 문장 클릭으로 수정할 수 있습니다.")
'''
old_service = '''        "The contract document language in current_snapshot.language is separate; "
        "do not use it to determine the chat language.",
'''
new_service = '''        "The contract document language in current_snapshot.language is separate; "
        "do not use it to determine the chat language. "
        "Ask NO MORE THAN TWO essential, non-overlapping questions across the entire conversation. "
        "Never repeat a question already asked or answered in messages; if an answer is provisional, "
        "record it as suggested instead of asking again. After a user answers follow-ups, "
        "return zero more questions. Lack of a bank account, registered address, or legal opinion "
        "should be recorded as a missing item for signature, not prevent an initial draft.",
'''
old_draft = '''        "Reconcile material conflicts in issues and ask for missing terms. Do not silently discard user cautions. "
'''
new_draft = '''        "Reconcile material conflicts in issues but do not ask questions before writing the draft. "
        "Use explicit placeholders such as [서명 전 확인] or [TO CONFIRM] for unresolved facts; "
        "do not invent or falsely certify missing terms. Draft the full usable clause structure first. "
        "Do not silently discard user cautions. "
'''

ui_text = UI.read_text(encoding='utf-8')
service_text = SERVICE.read_text(encoding='utf-8')
if HELPER.exists():
    raise RuntimeError('contracts/flow.py already exists; inspect changes before running. No files modified.')
ui_text = replace_once(ui_text, old_import, new_import, 'UI import')
ui_text = replace_once(ui_text, old_process, new_process, 'UI post-analysis flow')
ui_text = replace_once(ui_text, old_response, new_response, 'UI draft response')
ui_text = replace_once(ui_text, old_questions, new_questions, 'UI question expander')
ui_text = replace_once(ui_text, old_hint, new_hint, 'UI hint')
service_text = replace_once(service_text, old_service, new_service, 'analysis prompt')
service_text = replace_once(service_text, old_draft, new_draft, 'draft prompt')
for path, content in ((UI, ui_text), (SERVICE, service_text), (HELPER, flow)):
    ast.parse(content, filename=str(path))
# Write only after all anchors and syntax verified.
UI.write_text(ui_text, encoding='utf-8')
SERVICE.write_text(service_text, encoding='utf-8')
HELPER.write_text(flow, encoding='utf-8')
print('Updated only contracts/ui.py, contracts/service.py and new contracts/flow.py.')
print('Explicit draft requests generate draft without another question round.')
print('Existing export validation and other product workflows are unchanged.')
