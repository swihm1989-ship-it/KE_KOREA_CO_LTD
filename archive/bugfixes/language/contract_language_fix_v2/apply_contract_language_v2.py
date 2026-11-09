"""Patch only contract AI follow-up localization; run at repository root.

Stops without writing if source structure differs or this patch was applied already.
"""
from pathlib import Path
import ast
import sys

root = Path.cwd()
p = root / 'Quotation_KEKOREA' / 'contracts' / 'service.py'
if not p.exists():
    sys.exit('ERROR: Run at KE_KOREA_CO_LTD repository root. No files modified.')
src = p.read_text(encoding='utf-8')
marker = 'def _localize_contract_followups('
if marker in src:
    print('Already applied; no changes made.')
    sys.exit(0)
if 'def conversation_response_language(' not in src:
    sys.exit('ERROR: The previous language policy patch is missing. No files modified.')

helper = '''def _localize_contract_followups(data, language, *, env, opener):
    """Localize AI-generated questions without changing transaction facts/terms.

    An explicit second call is used only when questions/issue text ignores the
    language rule. Invalid translations fail closed rather than saving English
    output as if the language requirement had been satisfied.
    """
    questions = data["questions"]
    issues = data["issues"]
    original = [*questions, *(issue["message"] for issue in issues)]
    def correct_language(value):
        has_hangul = bool(re.search(r"[\\uac00-\\ud7a3\\u1100-\\u11ff\\u3130-\\u318f]", value))
        return has_hangul if language == "ko" else not has_hangul

    bad_indices = [index for index, value in enumerate(original)
                   if not correct_language(value)]
    if not bad_indices:
        return data

    translated = _call(
        "You are a precise bilingual business-contract question translator. "
        "Translate each numbered input string into natural Korean if target_language=ko, "
        "or natural English if target_language=en. "
        "Return JSON exactly {\\"translations\\": [strings]} in the same order and count. "
        "Preserve numeric figures, percentages, USD amounts, legal entity names, "
        "proper nouns, and meaning. Do not answer questions, add facts, interpret a "
        "jurisdiction, or change any commercial term. "
        "For target_language=ko every output must contain Korean writing; "
        "English labels and names may remain unchanged within Korean sentences.",
        {"target_language": language, "texts": [original[i] for i in bad_indices]},
        env=env, opener=opener,
    )
    outputs = translated.get("translations")
    if (not isinstance(outputs, list) or len(outputs) != len(bad_indices)
            or not all(isinstance(value, str) and value.strip() and
                       correct_language(value) for value in outputs)):
        raise RuntimeError("Contract AI could not produce questions in the requested conversation language; no new analysis was saved.")
    localized = list(original)
    for index, value in zip(bad_indices, outputs):
        localized[index] = value
    data["questions"] = localized[:len(questions)]
    for issue, message in zip(issues, localized[len(questions):]):
        issue["message"] = message
    return data


'''
anchor = 'def analyze_trade(messages, current_snapshot, reference_context, *, env, client=None):\n'
if src.count(anchor) != 1:
    sys.exit(f'ERROR: expected analyze_trade exactly once; found {src.count(anchor)}. No files modified.')
# The no-message path is used by legacy service tests, not chat. Preserve the
# snapshot language when there is no user message at all.
old_default = '    response_language = conversation_response_language(latest_user_text)\n'
new_default = ('    response_language = (conversation_response_language(latest_user_text) if latest_user_text\n'
               '                         else (current_snapshot.get("language") or "en"))\n')
if src.count(old_default) != 1:
    sys.exit('ERROR: response-language selector not found exactly once. No files modified.')
src = src.replace(old_default, new_default, 1)
start = src.index(anchor)
next_fn = src.find('\ndef generate_draft(', start)
if next_fn < 0:
    sys.exit('ERROR: Could not identify analyze_trade end. No files modified.')
segment = src[start:next_fn]
end_line = '    return data\n'
if segment.count(end_line) != 1:
    sys.exit(f'ERROR: expected return data once in analyze_trade; found {segment.count(end_line)}. No files modified.')
segment = segment.replace(end_line, '    return _localize_contract_followups(data, response_language, env=env,\n                                          opener=client or urllib.request.urlopen)\n', 1)
new_src = src[:start] + segment + src[next_fn:]
new_src = new_src.replace(anchor, helper + anchor, 1)
try:
    ast.parse(new_src)
except SyntaxError as exc:
    sys.exit(f'ERROR: generated Python syntax invalid: {exc}. No files modified.')
p.write_text(new_src, encoding='utf-8')
print('Updated only Quotation_KEKOREA/contracts/service.py (AI question/issue language fallback).')
