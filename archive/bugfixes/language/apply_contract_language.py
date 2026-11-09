"""Apply a narrowly scoped contract-chat language patch to KE_KOREA_CO_LTD checkout."""
from pathlib import Path
import sys

ROOT = Path.cwd()
BASE = ROOT / 'Quotation_KEKOREA'
service_path = BASE / 'contracts/service.py'
ui_path = BASE / 'contracts/ui.py'
if not service_path.is_file() or not ui_path.is_file():
    raise SystemExit('ERROR: Run from the KE_KOREA_CO_LTD repository root.')

service = service_path.read_text(encoding='utf-8')
ui = ui_path.read_text(encoding='utf-8')


def replace_once(body, old, new, title):
    count = body.count(old)
    if count != 1:
        raise SystemExit(f'ERROR: {title}: expected 1 code match, found {count}. No files modified.')
    return body.replace(old, new, 1)

helper = '''def conversation_response_language(text):
    """Select Korean for any Hangul; use English only for English-only input."""
    value = str(text or "")
    if re.search(r"[\\uac00-\\ud7a3\\u1100-\\u11ff\\u3130-\\u318f]", value):
        return "ko"
    if re.search(r"[A-Za-z]", value):
        return "en"
    return "ko"


'''
service = replace_once(service, 'def requested_language(text):\n', helper + 'def requested_language(text):\n', 'language detection')
service = replace_once(service,
'''    user_data = {
        "messages": messages,
        "current_snapshot": current_snapshot,
        "reference_context": reference_context,
    }
    data = _call(
''',
'''    latest_user_text = next((str(message.get("content") or "") for message in reversed(messages)
                             if message.get("role") == "user"), "")
    response_language = conversation_response_language(latest_user_text)
    user_data = {
        "messages": messages,
        "current_snapshot": current_snapshot,
        "reference_context": reference_context,
        "conversation_response_language": response_language,
    }
    data = _call(
''', 'response language context')
service = replace_once(service,
'''        "Do not state that terms are legally enforceable or legally compliant.",
''',
'''        "Do not state that terms are legally enforceable or legally compliant. "
        "For questions and issues.message, follow conversation_response_language from user_data: "
        "ko means natural Korean only (except unavoidable proper names and standard codes), "
        "en means natural English only. Korean or mixed Korean-English user messages MUST receive Korean questions. "
        "English-only user messages MUST receive English questions. "
        "The contract document language in current_snapshot.language is separate; "
        "do not use it to determine the chat language.",
''', 'AI question language instruction')

ui = replace_once(ui,
'''    analyze_trade, extract_reference_page, generate_draft, language_conflict,
''',
'''    analyze_trade, conversation_response_language, extract_reference_page, generate_draft, language_conflict,
''', 'UI language import')
ui = replace_once(ui,
'''            response = (f"거래조건을 분석했습니다. 조건 후보 {len(analysis.get('terms', []))}개, "
                        f"확인할 질문 {len(analysis.get('questions', []))}개입니다.")
            if analysis.get("questions"):
                response += "\\n\\n확인할 사항:\\n" + "\\n".join(
                    f"- {question}" for question in analysis["questions"][:5])
            if snapshot.get("clauses"):
                response += "\\n\\n기존 계약 내용은 자동 덮어쓰지 않았습니다. 아래 분석 후보를 검토해 적용하세요."
''',
'''            response_language = conversation_response_language(prompt)
            if response_language == "en":
                response = (f"Trade terms analyzed: {len(analysis.get('terms', []))} candidates, "
                            f"{len(analysis.get('questions', []))} questions to clarify.")
            else:
                response = (f"거래조건을 분석했습니다. 조건 후보 {len(analysis.get('terms', []))}개, "
                            f"확인할 질문 {len(analysis.get('questions', []))}개입니다.")
            if analysis.get("questions"):
                response += ("\\n\\nQuestions to clarify:\\n" if response_language == "en"
                             else "\\n\\n확인할 사항:\\n") + "\\n".join(
                    f"- {question}" for question in analysis["questions"][:5])
            if snapshot.get("clauses"):
                response += ("\\n\\nThe existing draft was not overwritten. Review the analysis candidates below before applying them."
                             if response_language == "en"
                             else "\\n\\n기존 계약 내용은 자동 덮어쓰지 않았습니다. 아래 분석 후보를 검토해 적용하세요.")
''', 'chat reply language')

# Persist only once every replacement succeeded, to avoid partial changes.
service_path.write_text(service, encoding='utf-8')
ui_path.write_text(ui, encoding='utf-8')
print('Updated only contracts/service.py and contracts/ui.py')
