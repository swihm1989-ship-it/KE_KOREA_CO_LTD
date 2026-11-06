"""Apply the TASTE-informed contract review UI and synchronize project READMEs.

Run once from the KE_KOREA_CO_LTD repository root.
Transactional per file, with exact-anchor preflight and rollback on write error.
No external calls, no database mutations, and no automatic commits.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
PKG = Path(__file__).resolve().parent
Q = ROOT / 'Quotation_KEKOREA'
UI = Q / 'contracts/ui.py'
HELPER = Q / 'contracts/review_summary.py'
TEST = Q / 'tests/test_contract_review_summary.py'
GUARD_TEST = Q / 'tests/test_readme_sync_guard.py'
DOCS = [
    ROOT / 'README.md',
    Q / 'README.md',
    Q / 'README_CONTRACTS.md',
    Q / 'Team/README.md',
    Q / 'Presentation/README.md',
]
AGENTS = Q / 'AGENTS.md'
GUARD = ROOT / 'scripts/check_readme_sync.py'
HOOK = ROOT / '.githooks/pre-commit'
TAG = '2026-11-06 TASTE 계약서 UI 및 README 동기화'

if not all(p.is_file() for p in [UI, AGENTS, *DOCS, Q / 'contracts/rules.py']):
    raise SystemExit('ERROR: Run in the KE_KOREA_CO_LTD project root; expected files missing. Nothing changed.')
if TAG in (Q / 'README_CONTRACTS.md').read_text(encoding='utf-8'):
    raise SystemExit('ERROR: This update has already been applied. Nothing changed.')
if HELPER.exists() or TEST.exists() or GUARD_TEST.exists():
    raise SystemExit('ERROR: review_summary.py or its test already exists; do not overwrite a previous patch. Nothing changed.')

files = {p: p.read_text(encoding='utf-8') for p in [UI, AGENTS, *DOCS]}

def replace_exact(s: str, old: str, new: str, path: Path) -> str:
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f'Unexpected source layout in {path}: expected one occurrence of {old[:60]!r}, found {n}. No files modified.')
    return s.replace(old, new, 1)

def append_section(path: Path, heading: str, text: str):
    if heading in files[path]:
        raise RuntimeError(f'Duplicate section in {path}; no files modified.')
    files[path] = files[path].rstrip() + '\n\n' + heading + '\n\n' + text.strip() + '\n'

# UI: preserve all raw findings and their historical resolution data, and never
# remove deterministic final-export validation.
s = files[UI]
imports = 'from Quotation_KEKOREA.contracts.library import search_library\n'
s = replace_exact(s, imports, imports + 'from Quotation_KEKOREA.contracts.review_summary import summarize_issues, unresolved_issues\n', UI)
old_caption = '        st.caption(f"미확정·검토 항목 {len(snapshot[\'issues\'])}개는 계약서 본문 아래에서 확인할 수 있습니다.")'
new_caption = '        st.caption("초안은 바로 수정할 수 있습니다. 미확정 사항은 아래의 서명 전 확인 메뉴에서 검토합니다.")'
s = replace_exact(s, old_caption, new_caption, UI)
start_marker = '    if snapshot.get("issues"):\n        with st.expander(f"검토 사항 ({len(snapshot[\'issues\'])}개) · 필요할 때 열기", expanded=False):\n'
end_marker = '\n\ndef _export_panel(repo, snapshot, env):'
if s.count(start_marker) != 1 or s.count(end_marker) != 1:
    raise RuntimeError('Unexpected review UI block. No files modified.')
start = s.index(start_marker)
end = s.index(end_marker, start)
original_body = s[start + len(start_marker):end].rstrip('\n')
# Keep the original issue-resolution controls and save action in a sibling expander.
# Nested st.expander is not supported by Streamlit.
summary_block = '''    if snapshot.get("issues"):
        unresolved = unresolved_issues(snapshot["issues"])
        if unresolved:
            st.markdown("#### 서명 전 확인사항")
            st.caption(f"미확정 {len(unresolved)}건 · 계약서 초안 작성 및 문장 수정은 계속할 수 있습니다.")
            with st.expander("핵심 확인 항목 보기", expanded=False):
                for group in summarize_issues(snapshot["issues"]):
                    st.markdown(f"**{group['label']}** · {group['count']}건")
                    st.caption(group["guidance"])
        with st.expander(f"상세 검토 및 확인 근거 입력 ({len(snapshot['issues'])}건)", expanded=False):
'''
s = s[:start] + summary_block + original_body + '\n' + s[end:]
old_export = '''    if issues:
        st.warning("확인되지 않은 조건이나 충돌이 있어 검토용 파일 내보내기를 막았습니다.")
        for issue in issues:
            st.write(f"- {issue['message']}")
        return
'''
new_export = '''    if issues:
        st.warning("서명 전 확인이 필요한 사항이 남아 있어 최종 파일 생성이 제한됩니다. 초안 수정은 계속할 수 있습니다.")
        for group in summarize_issues(issues):
            st.markdown(f"**{group['label']}** · {group['count']}건")
            st.caption(group["guidance"])
        with st.expander(f"최종 검증 항목 전체 보기 ({len(issues)}건)", expanded=False):
            for issue in issues:
                st.write(f"- {issue.get('message', '')}")
        return
'''
s = replace_exact(s, old_export, new_export, UI)
files[UI] = s

# Make the top-level README's description accurate while preserving quotation logic.
root = DOCS[0]
files[root] = replace_exact(files[root], '견적서 및 회사 에이전트 모음',
    '무역 문서 및 AI 계약서 작성·검토 워크스페이스', root)
append_section(root, f'## {TAG}', '''- 기존 PO·PI·CI·PL 문서 자동화와 별도로 한국어/영어 계약서 초안, 대화 기반 조건 추출, 문장별 수정·비교·revision 저장 기능을 제공한다.
- 계약서 기능은 초안 중심 작업 흐름을 유지하고, 검토 이슈를 한국어로 최대 5개 주제로 요약한다. 기존 원본 검토 기록과 최종 내보내기 검사 규칙은 유지한다.
- 계약서에는 참고 문서와 승인된 조항의 검색(RAG) 기반 위험 검토가 포함되며, 위험 검토와 AI 분석은 자동으로 법률 검증을 완료한 것으로 취급하지 않는다.
- 수수료 계약의 지급기한·연체이율은 입력·갱신할 수 있다. 기본 D+7은 초기 제안일 뿐 사용자 합의 내용을 자동으로 덮어쓰지 않는다.
- 변경 시 프로젝트, 계약서, 팀, 발표용 README를 코드와 함께 동기화한다. [변경 보호 지침](Quotation_KEKOREA/AGENTS.md) 및 `scripts/check_readme_sync.py` 참고.
- GitHub 코드 반영, 로컬 테스트, 실제 Streamlit 운영 확인은 각각 구분한다.''')

project = DOCS[1]
files[project] = files[project].replace('최종 갱신: 2026-11-05 (Asia/Seoul)', '최종 갱신: 2026-11-06 (Asia/Seoul)', 1)
files[project] = files[project].replace(
    '계약 코드는 로컬에 추가되었으며, Supabase migration 적용과 운영 배포는 완료된 것으로 간주하지 않는다.',
    '계약 코드는 GitHub `main`에 반영되었지만 Supabase migration 적용·운영 데이터 저장·실제 Streamlit 경로의 동작은 별도로 검증해야 한다.', 1)
append_section(project, f'### {TAG}', '''- **현재 코드 기준:** `contracts/flow.py`는 반복 질문을 줄이고 초안 작성 요청에 따라 초안을 만든다. 질문 응답과 계약서 본문 언어는 별개로 관리한다.
- **지급조건:** `contracts/commission_policy.py`와 UI에서 커미션 지급기한 및 서면합의 연체이율을 반영한다. 초기 D+7을 사용자가 변경할 수 있으며, 계좌 및 법률 검증의 미확정 상태는 유지한다.
- **RAG:** 승인된 참고 조항 검색 결과를 위험 검토에 활용하지만, 자동 승인을 하지 않는다. 참고 자료는 거래 당사자·금액 등을 확정하는 근거로 자동 승격하지 않는다.
- **TASTE 기반 검토 UI:** 계약서 본문 우선, 미확정 이슈 5개 이내 한국어 그룹, 원본 문제별 근거 입력은 접힌 고급 섹션, 최종 DOCX/PDF 내보내기 검증은 변경하지 않는다. 외부 디자인 의존성 없이 Streamlit 사용.
- **검증 이력:** 사용자 로컬에서 2026-11-06 지급조건 수정까지 계약서 관련 74개 테스트 `OK`, 커밋 `f9e7d05`의 GitHub `main` 푸시 성공을 보고했다. 이번 TASTE 수정은 별도의 로컬 전체 테스트와 실제 배포 검증이 필요하다. 과거 테스트 수·실패 기록은 각 날짜의 이력으로 해석한다.
- **문서 동기화:** 5개 README에 기능 변경·변경된 설명·제거한 기능을 함께 반영한다. `scripts/check_readme_sync.py` 및 `.githooks/pre-commit` 검사 포함. 자세한 계약 동작은 [README_CONTRACTS.md](README_CONTRACTS.md) 참조.''')

contracts = DOCS[2]
# A precise replacement of statements superseded by newly committed features.
files[contracts] = replace_exact(files[contracts],
    'For existing drafts use `기본 지급 조항 적용 / 갱신`.',
    'For existing drafts use `수수료 지급조건 수정` to set or revise the trigger, deadline, payer country and a negotiated annual late-interest rate; save to generate the corresponding payment sections. The `기본 지급 조항 적용 / 갱신` action remains available for refreshing stored policy clauses.', contracts)
files[contracts] = files[contracts].replace(
    'locally assembled payment sections require each confirmed trigger/tranche to be paid within seven calendar days by TT;',
    'locally assembled payment sections default to D+7 calendar days after each confirmed trigger/tranche by TT, while explicitly confirmed custom deadlines can be used;', 1)
files[contracts] = files[contracts].replace(
    'Default interest runs as daily simple interest on unpaid principal from the day after the due date, absent a bilateral written variation.',
    'Default interest runs as daily simple interest on unpaid principal from the day after the due date; the edit form accepts an explicitly negotiated annual percentage while legal validity remains a separate review requirement.', 1)
append_section(contracts, f'## {TAG}', '''### Current drafting and review flow

- **Draft first:** Users enter a natural-language transaction, respond to at most a small number of initial clarifying questions, and generate a complete working draft. Draft generation and sentence edits remain possible while legal details are unresolved.
- **Sentence revisions:** Select a sentence, write an instruction, generate the AI proposal, compare and approve; the accepted change saves as a new revision. No automatic rewriting of user-approved legal terms.
- **Review UI:** `contracts/review_summary.py` groups unresolved AI findings into up to five Korean topics, shows the count of original findings and leaves full original English/Korean findings plus user notes intact under advanced review. Grouping is presentation-only, not deduplication of actual legal checks.
- **Final validation:** `contracts/rules.py` and payment policy checks remain authoritative for document export. A summary must never change the underlying issue status, user confirmation, evidence, bank settings or signature readiness. Information marked 'user supplied' is not equivalent to independently verified.
- **Commission editor:** The payment trigger, payer country, due period and optionally negotiated late-interest rate may be edited. Bank details and enforceability must be verified before final export; no guessed addresses or numeric rates.
- **RAG risk assessment:** Optional, source-grounded risk review based on approved sample clauses. Its AI suggestions do not modify a contract until the user explicitly applies them.
- **Rollout:** Commit `f9e7d05` (payment editor) was pushed and 74 contract-related tests passed locally according to the user. This TASTE patch and README synchronization still require tests on the user's checkout. GitHub presence is not evidence of live Streamlit deployment or production Supabase configuration.

### Scope and privacy

No change to PO/PI/CI/PL or ECLADO pricing logic. The current contract page is not authenticated; do not use live confidential agreements on an internet-accessible instance until access control is added and tested. Never put bank account data or API keys in a README.''')

team = DOCS[3]
files[team] = files[team].replace('**기준일: 2026-11-05**', '**기준일: 2026-11-06**', 1)
append_section(team, f'## {TAG}', '''### 계약서 워크스페이스 운영 및 유지보수

- 메뉴는 PO/PI/CI/PL과 **계약서 만들기**로 구분한다. 기존 견적서 계산과 가격 정책은 변경하지 않는다.
- 자연어 거래 입력 → 반복 질문 제한 → 한국어/영어 초안 → 문장 선택/AI 수정 제안 → 명시적 승인/revision 기록 → 서명 전 최종 검증 → DOCX/PDF 출력의 흐름이다.
- 검토 화면은 `contracts/review_summary.py`를 이용해 미확정 항목을 최대 다섯 개 한국어 주제로 표시한다. 원본 AI finding, 증빙/확인 입력과 `rules.py`의 수출 검증은 훼손하지 않는다.
- 커미션 지급조건은 기본 D+7·TT에서 출발하지만 사용자가 지급기한과 서면합의 연체이율을 편집할 수 있다. 계좌/법률 정보는 AI가 임의 확정하지 않는다.
- `contracts/library.py`, `review.py` 등의 승인된 샘플 검색(RAG)은 **계약서 관련** 기능이다. 상품·가격 매칭은 별도의 SKU/용량 규칙을 계속 사용하며, 위에서 설명한 '상품에 벡터 DB 미사용' 규칙과 충돌하지 않는다.
- 과거 README에 적힌 테스트 실패·미배포 상태는 작성 시점의 기록이다. 사용자 로컬의 최근 계약 74개 테스트는 2026-11-06에 통과했으며, 새 UI 패치에 대한 전체 앱 테스트와 운영 환경 확인은 아직 필요하다.
- 코드 변경·삭제 시 루트/프로젝트/계약/Team/Presentation README를 동일 변경에서 갱신한다. `scripts/check_readme_sync.py`의 staged guard를 통과시키고 기존 기능 설명이 남아 있지 않은지 확인한다.''')

presentation = DOCS[4]
# Preserve historical QA details as an explicitly historical snapshot.
files[presentation] = files[presentation].replace(
    '이번 세션에서는 계약 목록의 `options` 오류를 소스 검토로 발견했습니다.',
    '아래 내용은 2026-11-06 이전 시점의 역사적 검토 기록입니다. 최신 상태는 다음 업데이트를 우선합니다. 계약 목록의 `options` 오류는 당시 소스 검토에서 발견했습니다.', 1)
append_section(presentation, f'## {TAG}', '''### 발표 메시지: AI가 초안을 만들고 사람이 통제한다

- **계약서 3단계 시연:** (1) 거래 설명만으로 초안 생성 (2) 문장 클릭 및 수정 제안 비교/승인 (3) 한국어로 묶인 핵심 확인사항 확인 후 최종 내보내기.
- **간결한 화면:** 수십 개의 AI 경고를 평소에는 표시하지 않고 최대 다섯 개의 주요 검토 그룹만 표시한다. 원본 항목과 근거 입력은 접힌 고급 메뉴로 유지한다.
- **안전성:** AI가 거래 상대방·계좌·법률 검토를 확정한 척하지 않는다. 미확정 정보가 있어도 초안은 편집 가능하며, DOCX/PDF 최종 생성 시 별도 규칙 검증을 한다.
- **기술:** 기존 Streamlit UI와 Supabase revision, 승인된 샘플 기반 RAG 위험 검토. 새로운 React/Next.js 디자인 시스템을 도입하지 않았다.
- **최신 검증:** 지급조건 편집 변경까지 사용자 로컬에서 계약 관련 74개 테스트가 통과했고, `f9e7d05`가 GitHub `main`에 업로드됐다. 이번 TASTE 검토 UI와 문서 동기화는 새 패치이므로 테스트 및 실제 Streamlit 배포 확인 전에는 완료된 시연 기능으로 발표하지 않는다.
- **시연 자료:** 합성 거래조건만 사용한다. 운영 앱 계약서 화면에는 인증이 없어 실제 계약서 시연은 금지한다.''')

append_section(AGENTS, f'## {TAG} 이후 README 자동 동기화 규칙', '''기능을 추가·수정·삭제할 때 같은 커밋에서 다음 다섯 파일을 함께 점검하고 필요한 내용을 고친다.

1. `../README.md` : 프로젝트 전체 기능/링크/배포 상태
2. `README.md` : 설계·변경 이력·테스트 결과
3. `README_CONTRACTS.md` : 계약 기능 실제 구현/제한사항
4. `Team/README.md` : 팀 구현·연동·위험 사항
5. `Presentation/README.md` : 시연할 수 있는 실제 기능과 검증 상태

변경 전 코드 설명이 더 이상 맞지 않으면 그 설명을 최신 동작으로 대체하고, 제거된 기능은 현재 동작 목록에서 빼거나 역사 기록으로 명확히 옮긴다. **코드만 바꾸고 README 업데이트를 생략하지 않는다.** 운영 확인이 안 된 경우 '미확인'을 유지하며, 과거 회귀 실패를 현재 실패로 단정하지 않는다.

`../scripts/check_readme_sync.py`는 스테이징된 프로젝트 실행 코드가 있으면 다섯 README가 같은 커밋에 모두 포함되는지 확인한다. `.githooks/pre-commit` 사용 시 로컬 커밋을 자동 검사한다. 이 검사는 문서의 진실성까지 보장하지 않으므로 사람의 리뷰와 테스트를 대체하지 않는다.
''')

# New content for helper/tests/guard and hook.
files[HELPER] = (PKG / 'review_summary.py').read_text(encoding='utf-8')
files[TEST] = (PKG / 'test_contract_review_summary.py').read_text(encoding='utf-8')
files[GUARD_TEST] = (PKG / 'test_readme_sync_guard.py').read_text(encoding='utf-8')
files[GUARD] = (PKG / 'check_readme_sync.py').read_text(encoding='utf-8')
files[HOOK] = '#!/bin/sh\n# Verify five README files accompany application code changes.\nexec python scripts/check_readme_sync.py\n'

for path, contents in files.items():
    if path.suffix == '.py':
        ast.parse(contents, filename=str(path))

# Write only after all checks. Save source-only backups outside tracked project.
backup_dir = PKG / ('backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup_dir.mkdir(exist_ok=False)
written = []
try:
    for path, contents in files.items():
        if path.exists():
            backup = backup_dir / path.relative_to(ROOT)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding='utf-8')
        written.append(path)
    HOOK.chmod(0o755)
except Exception:
    for path in reversed(written):
        backup = backup_dir / path.relative_to(ROOT)
        if backup.exists():
            shutil.copy2(backup, path)
        else:
            path.unlink(missing_ok=True)
    raise

# Do not silently override an existing user-defined hook configuration.
installed = False
try:
    current = subprocess.run(['git', 'config', '--local', '--get', 'core.hooksPath'],
                             cwd=ROOT, capture_output=True, text=True).stdout.strip()
    native_hook = ROOT / '.git/hooks/pre-commit'
    if not current and not native_hook.exists():
        subprocess.run(['git', 'config', '--local', 'core.hooksPath', '.githooks'],
                       cwd=ROOT, check=True, capture_output=True)
        installed = True
    elif current == '.githooks':
        installed = True
except (OSError, subprocess.CalledProcessError):
    pass

print(f'Updated {len(files)} source/docs/guard files. Backup: {backup_dir}')
print('README guard enabled:', installed)
if not installed:
    print('Existing Git hook settings were kept. Enable manually only after reviewing: git config core.hooksPath .githooks')
print('Next: run contract tests and full suite; inspect staged README changes before commit.')
