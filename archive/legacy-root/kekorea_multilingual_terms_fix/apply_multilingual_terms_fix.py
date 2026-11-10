"""Apply language-independent clause term-key normalization to KE KOREA.
Run from the repository root. Makes timestamped backups; rerunnable safely.
"""
from pathlib import Path
import shutil
import sys
from datetime import datetime

ROOT = Path.cwd()
TARGET = ROOT / 'Quotation_KEKOREA/contracts'
if not (TARGET/'service.py').exists() or not (TARGET/'clause_terms.py').exists():
    raise SystemExit('Please run this script from the KE_KOREA_CO_LTD repository root.')

service_path = TARGET/'service.py'
bridge_path = TARGET/'clause_terms.py'
service = service_path.read_text(encoding='utf-8')
bridge = bridge_path.read_text(encoding='utf-8')
assert 'def merge_clause_candidates(snapshot, analysis):' in bridge
assert 'def analyze_trade(messages, current_snapshot, reference_context, *, env, client=None):' in service

# Instruct extraction to return canonical keys regardless of input language.
needle = '"Each party has legal_name, country, address, representative, roles (array of buyer/seller/client/intermediary/commission_payer/fundraiser/investor). "'
addition = ('"Input clauses may be written in Korean, English, Indonesian, or other languages. Interpret each language equally, but ALWAYS use language-neutral English snake_case keys for terms. "\n        '
            '"Use exact standard keys: products, quantity, unit, unit_price, currency, payment_trigger, payment_deadline, delivery, inspection_claims, contract_date, scope, governing_law, dispute_resolution; use contract_duration, monthly_quantity_mt, total_contract_quantity for supplementary facts. "\n        '
            '"For example 단가/harga satuan/unit price => unit_price; 월 물량/jumlah bulanan/monthly quantity => quantity; 인도조건/syarat pengiriman/delivery terms => delivery; 대금 지급/syarat pembayaran/payment terms => payment_trigger. "\n        '
            '"Put buyer and seller LEGAL ENTITY NAMES only under parties with buyer/seller roles, not as terms. Preserve source wording, exact units, figures, currency and uncertainty. Do not translate company names or infer missing facts. "\n        ')
if 'Input clauses may be written in Korean, English, Indonesian' not in service:
    if needle not in service:
        raise SystemExit('service.py extraction prompt layout differs; no files changed.')
    service = service.replace(needle, addition + needle, 1)

# Normalize in the clause-specific bridge; existing ordinary chat paths unaffected.
old_import = 'from copy import deepcopy\n'
new_import = 'from copy import deepcopy\nfrom Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys\n'
if new_import not in bridge:
    bridge = bridge.replace(old_import, new_import, 1)
old_merge = '''    staged = deepcopy(snapshot)
    existing = {str(t.get('key')): t for t in staged.get('terms', [])}
    for candidate in analysis.get('terms', []):'''
new_merge = '''    staged = deepcopy(snapshot)
    analysis, conflicts = normalize_term_keys(analysis)
    # Preserve ambiguities for human review. Never auto-certify any extraction.
    if conflicts:
        staged['clause_extraction_conflicts'] = conflicts
    existing = {str(t.get('key')): t for t in staged.get('terms', [])}
    for candidate in analysis.get('terms', []):'''
if new_merge not in bridge:
    if old_merge not in bridge:
        raise SystemExit('clause_terms.py merge shape differs; no files changed.')
    bridge = bridge.replace(old_merge, new_merge, 1)

ui_path = TARGET/'ui.py'
ui = ui_path.read_text(encoding='utf-8')
needle_ui = "    if candidate_key in st.session_state:\n        st.info('본문에서 찾은 조건이 입력표에 AI 제안으로 나타납니다. 실제 값과 당사자 정보를 검토하고 상태를 확정한 뒤 기존 저장 버튼을 누르세요. 아직 원본은 변경되지 않았습니다.')"
replacement_ui = needle_ui + "\n        for conflict in editor_snapshot.get('clause_extraction_conflicts', []):\n            st.warning(f\"서로 다른 추출값이 발견되었습니다: {conflict['key']} · {conflict['first']} / {conflict['other']}. 원문을 확인하세요.\")"
if 'clause_extraction_conflicts' not in ui:
    if needle_ui not in ui:
        raise SystemExit('ui.py candidate information shape differs; no files changed.')
    ui = ui.replace(needle_ui, replacement_ui, 1)

readmes = [ROOT/'README.md',ROOT/'Quotation_KEKOREA/README.md',ROOT/'Quotation_KEKOREA/README_CONTRACTS.md', ROOT/'Quotation_KEKOREA/Team/README.md',ROOT/'Quotation_KEKOREA/Presentation/README.md']
for p in readmes:
    if not p.exists():
        raise SystemExit(f'Missing required README: {p}')

changed = {service_path:service,bridge_path:bridge,ui_path:ui}
new_module = TARGET/'normalize_terms.py'
if not new_module.exists():
    changed[new_module] = (Path(__file__).parent/'normalize_terms.py').read_text(encoding='utf-8')

note = ('\n## 2026-11-09 다국어 계약 조건 추출 키 정규화\n\n'
        '- BOX 2 본문 후보 추출 시 한국어·영어·인도네시아어 입력을 동일한 내부 snake_case 조건 키에 대응한다. 제품/단가/수량/인도/지급조건을 임의의 새 키로 중복 등록하지 않도록 주요 별칭을 정규화한다.\n'
        '- buyer/seller는 당사자 별도 표에서 확인하며 값·단위·통화 원문을 보존한다. AI 추출은 `suggested` 후보이며 사람이 `확정`해야만 confirmed가 된다. 기존 비어 있지 않은 값은 덮어쓰지 않는다.\n'
        '- 서로 다른 값이 하나의 표준 키에 충돌하면 첫 후보만 미승인으로 제시하고 경고를 표시한다. 자동 해결/기존 확정값 변경은 하지 않는다.\n'
        '- DRAFT/FINAL 출력 및 법적 최종 검증은 변경하지 않는다. 로컬 회귀 테스트와 실제 Streamlit 배포 검증은 별개이다.\n')
for p in readmes:
    current = p.read_text(encoding='utf-8')
    if '## 2026-11-09 다국어 계약 조건 추출 키 정규화' not in current:
        changed[p] = current.rstrip()+'\n'+note

# Test file is only installed once.
test_path = ROOT/'Quotation_KEKOREA/tests/test_contract_multilingual_terms.py'
if not test_path.exists():
    changed[test_path] = (Path(__file__).parent/'test_contract_multilingual_terms.py').read_text(encoding='utf-8')

actual = {p:c for p,c in changed.items() if not p.exists() or p.read_text(encoding='utf-8') != c}
if not actual:
    print('Already applied: no files changed.')
    sys.exit(0)
backup = ROOT / ('local_multilingual_patch_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
for p in actual:
    if p.exists():
        dest = backup/p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p,dest)
for p,c in actual.items():
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(c,encoding='utf-8')
print(f'Applied {len(actual)} files; originals backed up in {backup.name} (do not commit backup).')
