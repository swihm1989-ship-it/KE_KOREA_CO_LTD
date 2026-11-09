"""Conservative KE KOREA contract integrity patch. Run from repository root."""
from pathlib import Path
from datetime import datetime
import shutil
import sys
import ast

root=Path.cwd()
contracts=root/'Quotation_KEKOREA'/'contracts'
if not (contracts/'ui.py').exists() or not (contracts/'normalize_terms.py').exists():
    raise SystemExit('Run from KE_KOREA_CO_LTD repository root, after term-alias patch.')
base=Path(__file__).resolve().parent
replacement=(base/'normalize_terms.py').read_text(encoding='utf-8')
# Do not discard local alias additions: patch the current module selectively.
original=(contracts/'normalize_terms.py').read_text(encoding='utf-8')
start=original.index('def normalize_term_keys(analysis):')
replacement_function=replacement[replacement.index('def normalize_term_keys(analysis):'):]
if 'def _equivalent_terms(' not in original:
    original=original[:start]+replacement[replacement.index('def _extract_incoterm('):]
else:
    original=original[:original.index('def _extract_incoterm(')]+replacement[replacement.index('def _extract_incoterm('):]
# Need decimal imports for the new canonical comparison helpers.
if 'from decimal import Decimal, InvalidOperation' not in original:
    original=original.replace('from copy import deepcopy','from decimal import Decimal, InvalidOperation\nfrom copy import deepcopy',1)

path_draft=contracts/'draft_exports.py'
draft=path_draft.read_text(encoding='utf-8')
old="""            prefix = ('[확인 필요] ' if korean else '[TBD / UNCONFIRMED] ') if unresolved and not already_marked else ''"""
new="""            # A populated but unapproved candidate remains in the TBD appendix,
            # rather than being redundantly marked on every prose sentence.
            # A genuinely missing linked value still gets an inline warning.
            missing_linked = any(term is None or not str(term.get('value') or '').strip()
                                 for term in linked)
            prefix = ('[확인 필요] ' if korean else '[TBD / UNCONFIRMED] ') if missing_linked and not already_marked else ''"""
if new not in draft:
    if old not in draft: raise SystemExit('Unexpected draft_exports.py version; no files changed')
    draft=draft.replace(old,new,1)

path_rules=contracts/'rules.py'
rules=path_rules.read_text(encoding='utf-8')
needle="""    if for_export and snapshot.get("pending_reconciliation"):
"""
insert="""    if for_export:
        # Final files must not silently certify text still containing explicit
        # placeholders. DRAFT files remain available with review annotations.
        import re
        unresolved_pattern = re.compile(
            r'\\[(?:서명\\s*전\\s*확인|확인\\s*필요|TBD(?:\\s*/[^\\]]*)?|TO\\s*CONFIRM|'
            r'TO\\s*BE\\s*CONFIRMED|PENDING\\s*CONFIRMATION)\\]', re.IGNORECASE)
        for clause in snapshot.get('clauses', []):
            for sentence in clause.get('sentences', []):
                if unresolved_pattern.search(str(sentence.get('text') or '')):
                    issues.append({'severity': 'block', 'code': 'unresolved_clause_placeholder',
                                   'key': str(sentence.get('id') or ''),
                                   'message': '최종 계약서 본문에 미확정 표시가 남아 있습니다: '
                                              + str(sentence.get('text') or '')[:140]})
"""
if 'unresolved_clause_placeholder' not in rules:
    if needle not in rules: raise SystemExit('Unexpected rules.py version; no files changed')
    rules=rules.replace(needle,insert+needle,1)

path_service=contracts/'service.py'
service=path_service.read_text(encoding='utf-8')
needle_prompt='"Preserve exact numeric strings, currencies and units. Questions are strings. Issues must be objects with non-empty string code and message, "'
new_prompt='"For clause-to-term extraction, distinguish unit price from contract total, quantity amount from unit of measure, and Incoterm/location from delivery schedule/notice obligations. "\n        "Use ISO currency codes only when explicitly sourced; do not assume $ means USD. Cite exact source phrases for ambiguous claims and retain uncertainty rather than inventing data. "\n        "Never interpret a procedural delivery notice as contradictory to EXW, FOB, CIF or other Incoterms without actual inconsistent obligations. "\n        '
if 'distinguish unit price from contract total' not in service:
    if needle_prompt not in service: raise SystemExit('Unexpected service.py version; no files changed')
    service=service.replace(needle_prompt,new_prompt+needle_prompt,1)

readmes=[root/'README.md',root/'Quotation_KEKOREA/README.md',root/'Quotation_KEKOREA/README_CONTRACTS.md',root/'Quotation_KEKOREA/Team/README.md',root/'Quotation_KEKOREA/Presentation/README.md']
note=('\n## 2026-11-09 계약조건 추출·충돌 비교·FINAL 검증 강화\n\n'
      '- BOX 2 AI 추출은 한국어·영어·인도네시아어 표준 키 정규화를 유지하되 통화·단위·숫자·인도조건의 의미를 별도로 비교한다. **4와 5는 충돌**하나 `5`와 `5.00`은 수치가 같을 수 있으며, EXW 인도조건과 일정 협의 절차는 상호 배타적인 조건이 아니다. 근거가 불확실하면 미확정 후보로 남긴다.\n'
      '- 거래조건은 `AI 제안(suggested)`으로 표시하며 사용자가 승인하기 전까지 확정으로 승격되지 않는다. 기존 확정 조건은 자동 덮어쓰기하지 않는다. `$`만으로 USD를 가정하지 않는다.\n'
      '- DRAFT PDF/DOCX: 문장에 연결된 미확정 후보가 **값을 이미 보유한 경우** 중복 `[확인 필요]` 접두어 대신 미확정 부록과 DRAFT 경고로 관리한다. 실제 값이 빠진 연결 조항에는 계속 표시한다. 본문의 기존 `[서명 전 확인]`은 삭제하지 않는다.\n'
      '- FINAL PDF/DOCX: 서명 전 확인/TBD 등 명시적 미확정 표시가 본문에 남으면 기존 필수조건 검증에 더해 차단한다. Supabase 저장·다운로드, 법률/결제 검증과 Revision 흐름은 변경하지 않는다.\n'
      '- 수정사항 테스트: `Quotation_KEKOREA.tests.test_contract_integrity_fix`. 전체 회귀 및 실제 배포 파일 생성은 별개로 검증한다.\n')
changes={contracts/'normalize_terms.py':original,path_draft:draft,path_rules:rules,path_service:service}
tests=root/'Quotation_KEKOREA/tests/test_contract_integrity_fix.py'
changes[tests]=(base/'test_contract_integrity_fix.py').read_text(encoding='utf-8')
for path in readmes:
    if not path.exists(): raise SystemExit('Missing README '+str(path))
    old=path.read_text(encoding='utf-8')
    if '## 2026-11-09 계약조건 추출·충돌 비교·FINAL 검증 강화' not in old:
        changes[path]=old.rstrip()+'\n'+note
for path,data in changes.items():
    if path.suffix=='.py':ast.parse(data,filename=str(path))
actual={p:data for p,data in changes.items() if not p.exists() or p.read_text(encoding='utf-8')!=data}
if not actual:
    print('Already applied. No changes.');sys.exit(0)
backup=root/('local_integrity_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
for p in actual:
    if p.exists():
        dst=backup/p.relative_to(root)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dst)
for p,data in actual.items():
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(data,encoding='utf-8')
print('Patched',len(actual),'files; backed up originals to',backup.name)
print('Do not stage the installer directory or backups.')
