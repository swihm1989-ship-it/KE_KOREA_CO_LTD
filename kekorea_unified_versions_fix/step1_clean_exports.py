"""Apply a guarded patch to KE KOREA's contract export workflow.

Run from the repository root. Never overwrites files without verified anchors.
"""
from pathlib import Path
from datetime import datetime
from shutil import copy2
import ast
import sys

ROOT = Path.cwd()
BASE = ROOT / 'Quotation_KEKOREA' / 'contracts'
FILES = [BASE/'draft_exports.py', BASE/'exports.py', BASE/'ui.py', ROOT/'Quotation_KEKOREA/app.py', ROOT/'README.md', ROOT/'Quotation_KEKOREA/README.md', ROOT/'Quotation_KEKOREA/README_CONTRACTS.md', ROOT/'Quotation_KEKOREA/Team/README.md', ROOT/'Quotation_KEKOREA/Presentation/README.md']
for path in FILES:
    if not path.is_file():
        sys.exit('Required repo file missing: '+str(path))

def replace_once(text, old, new, name):
    n=text.count(old)
    if n!=1:
        raise RuntimeError(f'{name}: expected one anchor, found {n}; no files changed')
    return text.replace(old,new,1)

changed={}

# DRAFT: no warnings, annotations, appendix, or artificially injected markers.
p=BASE/'draft_exports.py'
s=p.read_text(encoding='utf-8')
start=s.index('    korean = snapshot[\'language\'] == \'ko\'\n',s.index('def export_draft('))
end=s.index('    result = {}\n',start)
new='''    korean = snapshot['language'] == 'ko'
    label = 'DRAFT / 검토용' if korean else 'DRAFT / FOR REVIEW'
    # Export only the authored clauses. Review issues stay inside BOX 2/the review panel.
    # Never inject [확인 필요] or append audit data to the contract document.
    lines = [(snapshot.get('title') or 'Contract', True)]
    for clause in sorted(snapshot['clauses'], key=lambda c: c.get('order', 0)):
        lines.append((clause.get('title') or '', True))
        for sentence in clause.get('sentences', []):
            lines.append((sentence['text'], False))
'''
s=s[:start]+new+s[end:]
# draft-only watermark/header allowed, no other review content
ast.parse(s)
changed[p]=s

# FINAL: seal only on the named KE KOREA party signature; no fake seal.
p=BASE/'exports.py'; s=p.read_text(encoding='utf-8')
s=replace_once(s,'from docx.shared import Inches, Pt','from docx.shared import Inches, Pt\nfrom pathlib import Path\nfrom reportlab.platypus import Image as PdfImage','exports imports')
s=replace_once(s,'def _docx(snapshot):','def _docx(snapshot, seal_bytes=None):','docx function')
s=replace_once(s,'def _pdf(snapshot):','def _pdf(snapshot, seal_bytes=None):','pdf function')
# target only signatory loops in two renderers
old='''    for party in snapshot.get("parties", []):
        roles = ", ".join(party.get("roles", []))
        document.add_heading(party.get("legal_name") or roles, level=2)
        document.add_paragraph("By: __________________________________")'''
new='''    for party in snapshot.get("parties", []):
        roles = ", ".join(party.get("roles", []))
        document.add_heading(party.get("legal_name") or roles, level=2)
        if seal_bytes is not None and _is_ke_korea_party(party):
            document.add_picture(io.BytesIO(seal_bytes), width=Inches(1.1))
        document.add_paragraph("By: __________________________________")'''
s=replace_once(s,old,new,'docx party signature')
old='''        story.extend([Paragraph(escape(label), heading_style),
                      Paragraph("By: __________________________________", body_style),'''
new='''        story.append(Paragraph(escape(label), heading_style))
        if seal_bytes is not None and _is_ke_korea_party(party):
            stamp = PdfImage(io.BytesIO(seal_bytes))
            stamp.drawHeight = 68
            stamp.drawWidth = 68 * stamp.imageWidth / stamp.imageHeight
            story.append(stamp)
        story.extend([Paragraph("By: __________________________________", body_style),'''
s=replace_once(s,old,new,'pdf party signature')
# Avoid rendering a second signature page when BOX 3 already contains one.
doc_sig_start=s.index('    document.add_page_break()\n',s.index('def _docx('))
doc_sig_end=s.index('    output = io.BytesIO()\n',doc_sig_start)
doc_sig_block=s[doc_sig_start:doc_sig_end]
s=s[:doc_sig_start]+(
    '    if _has_authored_signature_clause(snapshot):\n'
    '        if seal_bytes is not None:\n'
    '            document.add_picture(io.BytesIO(seal_bytes), width=Inches(1.1))\n'
    '    else:\n'+''.join('    '+line for line in doc_sig_block.splitlines(keepends=True))
)+s[doc_sig_end:]
pdf_sig_start=s.index('    story.append(PageBreak())\n',s.index('def _pdf('))
pdf_sig_end=s.index('    output = io.BytesIO()\n',pdf_sig_start)
pdf_sig_block=s[pdf_sig_start:pdf_sig_end]
s=s[:pdf_sig_start]+(
    '    if _has_authored_signature_clause(snapshot):\n'
    '        if seal_bytes is not None:\n'
    '            stamp = PdfImage(io.BytesIO(seal_bytes))\n'
    '            stamp.drawHeight = 68\n'
    '            stamp.drawWidth = 68 * stamp.imageWidth / stamp.imageHeight\n'
    '            story.append(stamp)\n'
    '    else:\n'+''.join('    '+line for line in pdf_sig_block.splitlines(keepends=True))
)+s[pdf_sig_end:]
s=replace_once(s,'def export_contract(snapshot, *, formats=("docx", "pdf")):','def export_contract(snapshot, *, formats=("docx", "pdf"), seal_bytes=None):','export function')
s=replace_once(s,'content = _docx(snapshot)','content = _docx(snapshot, seal_bytes=seal_bytes)','docx call')
s=replace_once(s,'content = _pdf(snapshot)','content = _pdf(snapshot, seal_bytes=seal_bytes)','pdf call')
s += '''\n\ndef _has_authored_signature_clause(snapshot):\n    titles = {'서명', '서명란', 'signatures', 'signature', 'signing'}\n    return any(str(c.get('title') or '').strip().casefold() in titles\n               for c in snapshot.get('clauses', []))\n\ndef _is_ke_korea_party(party):
    """Never place KE KOREA's company seal on another signatory."""
    name = re.sub(r'[^a-z0-9]', '', str(party.get('legal_name') or '').casefold())
    return name in {'kekorea', 'kekorealtd', 'kekoreacoltd', 'kekoreacolimited'}
'''
ast.parse(s); changed[p]=s

# Separate final blockers from internal completeness/advisory issues.
p=BASE/'final_policy.py'
s='''"""User-controlled FINAL export gate; review warnings are not contract text."""
import re

_PLACEHOLDER = re.compile(
    r'\\[(?:서명\\s*전\\s*확인|확인\\s*필요|필수\\s*확인|TBD(?:\\s*/[^\\]]*)?|'
    r'TO\\s*CONFIRM|TO\\s*BE\\s*CONFIRMED|PENDING\\s*CONFIRMATION)\\]', re.I)

def final_document_blockers(snapshot):
    """Block document placeholders and unreconciled changes, not every BOX 2 suggestion."""
    problems = []
    clauses = snapshot.get('clauses') or []
    if not any(str(s.get('text') or '').strip() for c in clauses for s in c.get('sentences', [])):
        problems.append('최종 계약서에 실제 계약 조항이 없습니다.')
    for clause in clauses:
        for sentence in clause.get('sentences', []):
            if _PLACEHOLDER.search(str(sentence.get('text') or '')):
                problems.append('BOX 3에 임시 확인 문구가 남았습니다: '+str(sentence.get('text') or '')[:90])
    if snapshot.get('pending_reconciliation'):
        problems.append('BOX 2 변경사항의 본문 반영·승인이 남아 있습니다.')
    parties = snapshot.get('parties') or []
    if not any(re.sub(r'[^a-z0-9]', '',str(p.get('legal_name') or '').casefold()) in
               {'kekorea', 'kekorealtd', 'kekoreacoltd', 'kekoreacolimited'} for p in parties):
        problems.append('서명 당사자에 KE KOREA가 없어 직인을 안전하게 날인할 수 없습니다.')
    if snapshot.get('contract_type') == 'sale':
        roles={role for p in parties for role in p.get('roles', [])}
        if not {'seller','buyer'}.issubset(roles):
            problems.append('매매계약의 매도인·매수인 서명 당사자가 모두 필요합니다.')
    return problems
'''
ast.parse(s);changed[p]=s

# UI: two-step user approval and a private password for automatic real-seal application.
p=BASE/'ui.py';s=p.read_text(encoding='utf-8')
s=replace_once(s,'import hashlib\nimport re','import hashlib\nimport hmac\nimport re\nfrom pathlib import Path','ui imports')
s=replace_once(s,'from Quotation_KEKOREA.contracts.exports import export_contract','from Quotation_KEKOREA.contracts.exports import export_contract\nfrom Quotation_KEKOREA.contracts.final_policy import final_document_blockers\nfrom Quotation_KEKOREA.agent.branding import resolve_company_seal, COMPANY_SEAL_SHA256','ui imports2')
start=s.index('def _export_panel(repo, snapshot, env):')
end=s.index('    draft_col, final_col = st.columns(2)',start)
new='''def _verified_contract_seal(env):
    """Load only the configured verified PNG, never a public URL or placeholder stamp."""
    root = Path(__file__).resolve().parents[1]
    path, blob, error = resolve_company_seal(root, env)
    if blob is None and path.is_file():
        blob = path.read_bytes()
    if (not blob or not blob.startswith(b'\\x89PNG\\r\\n\\x1a\\n')
            or hashlib.sha256(blob).hexdigest() != COMPANY_SEAL_SHA256):
        raise ValueError('검증된 KE KOREA 직인을 불러오지 못했습니다: '+str(error or '이미지 검증 실패'))
    return blob


def _export_panel(repo, snapshot, env):
    issues = validate_rules(snapshot, for_export=True, env=env)
    blockers = final_document_blockers(snapshot)
    st.markdown("#### 문서 다운로드")
    st.caption("DRAFT·FINAL에는 계약 본문과 서명란만 출력합니다. 내부 검토사항은 화면에서 확인하세요. "
               "FINAL은 승인한 현재 revision의 본문만 사용합니다.")
    if issues:
        st.warning(f"계약조건/법률 검토사항 {len(issues)}건이 남아 있습니다. PDF에는 포함하지 않으며, 최종 승인 전 검토하세요.")
    if blockers:
        for problem in blockers[:8]:
            st.error(problem)
    approval_key = f"contract_final_approved_{snapshot['contract_id']}_{snapshot['revision']}"
    approved = st.checkbox(
        "현재 revision의 계약 조항과 서명 당사자를 직접 확인했고 이 내용으로 FINAL을 생성하겠습니다.",
        key=approval_key)
    configured_password = str(env.get('CONTRACT_FINAL_SEAL_PASSWORD') or '')
    secret = st.text_input("FINAL 명판·직인 사용 암호 (관리자 전용)", type='password',
                           key=f"contract_final_seal_access_{snapshot['contract_id']}_{snapshot['revision']}")
    authorized = bool(configured_password) and hmac.compare_digest(secret, configured_password)
    if not configured_password:
        st.caption("관리자: Streamlit Secrets에 CONTRACT_FINAL_SEAL_PASSWORD를 설정해야 직인을 사용할 수 있습니다.")
    final_blocked = bool(blockers) or not approved or not authorized
'''
s=s[:start]+new+s[end:]
s=replace_once(s,"            if mode == 'final' and issues:\n                st.caption(f\"최종 확인이 필요한 항목 {len(issues)}건. BOX 2에서 실제 조건을 입력·확정하고, \"\n                           \"필요하면 아래 '고급 검토 기록'에서 AI 쟁점 근거를 확인하세요.\")\n",'', 'remove final old caption')
s=replace_once(s,"disabled=bool(issues) if mode == 'final' else False,","disabled=final_blocked if mode == 'final' else False,",'final button')
s=replace_once(s,"if mode == 'final' and validate_rules(snapshot, for_export=True, env=env):\n                            raise ValueError(\"최종 검증을 통과하지 못했습니다.\")","if mode == 'final' and (final_document_blockers(snapshot) or not approved or not authorized):\n                            raise ValueError('본문 승인 또는 직인 사용 권한 확인이 필요합니다.')",'final revalidation')
s=replace_once(s,"                        outputs = (export_draft(snapshot, formats=(extension,), env=env) if mode == 'draft'\n                                   else export_contract(snapshot, formats=(extension,)))","                        outputs = (export_draft(snapshot, formats=(extension,), env=env) if mode == 'draft'\n                                   else export_contract(snapshot, formats=(extension,),\n                                                        seal_bytes=_verified_contract_seal(env)))",'export call')
s=s.replace("if output and not (mode == 'final' and issues):","if output and not (mode == 'final' and final_blocked):")
s=s.replace("if local_output and not (mode == 'final' and issues):","if local_output and not (mode == 'final' and final_blocked):")
s=replace_once(s,"                if not draft and issues:\n                    continue","                if not draft and final_blocked:\n                    continue",'saved final access')
ast.parse(s); changed[p]=s

# Add focused regression tests.
test_path = ROOT / 'Quotation_KEKOREA/tests/test_contract_clean_exports.py'
if test_path.exists():
    raise RuntimeError('Test file already exists; inspect before patching')
changed[test_path] = (Path(__file__).parent/'test_contract_clean_exports.py').read_text(encoding='utf-8')

# Expose the new private seal password to the contract runtime.
app=ROOT/'Quotation_KEKOREA/app.py'
t=app.read_text(encoding='utf-8')
t = replace_once(t,
    '"CONTRACT_LIBRARY_ADMIN_TOKEN", "CONTRACT_LIBRARY_EMBEDDING_MODEL"):',
    '"CONTRACT_LIBRARY_ADMIN_TOKEN", "CONTRACT_LIBRARY_EMBEDDING_MODEL",\n                "CONTRACT_FINAL_SEAL_PASSWORD"):',
    'Streamlit secrets allowlist')
ast.parse(t); changed[app]=t

# Five protected README files must be staged together with implementation.
notice='''\n\n### 2026-11-09 계약 PDF 출력 정책 개선 (로컬 패치, 배포 미확인)\n- 계약서 DRAFT PDF/DOCX는 BOX 3에서 저장한 제목·조항을 출력하며, 검토용 워터마크/머리글은 유지하지만 자동 `[확인 필요]` 접두사, 미확정 부록, AI 검토 원문은 출력하지 않는다. 원래 조항 자체에 작성자가 적은 미확정 문구는 임의 삭제하지 않는다.\n- FINAL PDF/DOCX는 현재 revision의 본문을 사용자가 명시적으로 승인한 뒤 생성한다. BOX 2의 제안·법률 검토사항은 화면에서 경고하지만 전부 확정하도록 강제하지 않는다. 본문에 `[서명 전 확인]` 등의 임시 표시가 남았거나 당사자/본문이 명백히 누락되면 최종 생성을 막는다.\n- FINAL에는 검증된 회사 직인을 KE KOREA 서명란에만 넣는다. Streamlit Secrets의 `CONTRACT_FINAL_SEAL_PASSWORD` 관리자 암호가 필요하며 원본 이미지는 기존 비공개 Supabase 저장소 또는 SHA-256이 같은 로컬 이미지에서 읽는다. 이미지·비밀번호는 코드나 저장소에 기록하지 않는다. DRAFT에는 직인을 넣지 않는다.\n- 코드 패치가 전체 테스트나 운영 Streamlit 검증을 의미하지 않는다. 적용 후 테스트 및 실제 PDF 시각 검증이 필요하다.\n'''
for p in FILES[4:]:
    text=p.read_text(encoding='utf-8')
    if '### 2026-11-09 계약 PDF 출력 정책 개선' not in text:
        text += notice
    changed[p]=text

# Verify every file BEFORE any mutation.
for path,text in changed.items():
    if path.suffix=='.py':
        ast.parse(text,filename=str(path))
backups=ROOT / 'local_patch_backups' / ('clean_exports_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
for p in changed:
    if p.exists():
        backup=backups/p.relative_to(ROOT)
        backup.parent.mkdir(parents=True,exist_ok=True)
        copy2(p,backup)
for p,text in changed.items():
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text,encoding='utf-8')
print('Applied:',len(changed),'files; backup:',backups)
print('FINAL requires CONTRACT_FINAL_SEAL_PASSWORD in private Streamlit Secrets.')
print('Not deployed. Run full regression tests and inspect PDF before commit.')
