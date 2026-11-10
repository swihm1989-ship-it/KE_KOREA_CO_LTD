"""Single-entry, staged, guarded upgrade for the KE KOREA contract app.

Run from the repository root. Never commits/pushes or contacts external services.
"""
from pathlib import Path
import ast
import datetime as dt
import shutil
import subprocess
import sys
import tempfile

ROOT=Path.cwd()
HERE=Path(__file__).resolve().parent
REPO=ROOT/'Quotation_KEKOREA'
FILES=[
 'README.md','Quotation_KEKOREA/README.md','Quotation_KEKOREA/README_CONTRACTS.md',
 'Quotation_KEKOREA/Team/README.md','Quotation_KEKOREA/Presentation/README.md',
 'Quotation_KEKOREA/app.py','Quotation_KEKOREA/contracts/ui.py',
 'Quotation_KEKOREA/contracts/draft_exports.py','Quotation_KEKOREA/contracts/exports.py',
 'Quotation_KEKOREA/contracts/normalize_terms.py',
 'Quotation_KEKOREA/contracts/service.py',
 'Quotation_KEKOREA/contracts/final_policy.py',
 'Quotation_KEKOREA/contracts/latest_instruction.py',
 'Quotation_KEKOREA/tests/test_contract_three_box_ui.py',
 'Quotation_KEKOREA/tests/test_contract_export_storage_fallback.py',
 'Quotation_KEKOREA/tests/test_contract_clean_exports.py',
 'Quotation_KEKOREA/tests/test_contract_flow_repair.py',
 'Quotation_KEKOREA/tests/test_contract_latest_instruction.py',
 'Quotation_KEKOREA/contracts/contract_versions.py',
 'Quotation_KEKOREA/tests/test_contract_versions.py',
]
MANDATORY=FILES[:10]+[FILES[10], FILES[13],FILES[14]]
for name in MANDATORY:
    if not (ROOT/name).is_file():
        sys.exit('기존 프로젝트 루트에서 실행해 주세요. 파일이 없습니다: '+name)

if 'from Quotation_KEKOREA.contracts.contract_versions import copy_contract, translate_contract' in (ROOT/FILES[6]).read_text(encoding='utf-8'):
    print('이미 복사·번역 통합 패치가 설치되어 있습니다. 중복 변경하지 않았습니다.')
    sys.exit(0)

with tempfile.TemporaryDirectory(prefix='kekorea_unified_') as t:
    stage=Path(t)
    for name in FILES:
        src=ROOT/name
        if src.exists():
            dst=stage/name
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,dst)
    # Stage supporting project Python modules for integration tests. The preceding
    # FILES list intentionally contains only files that this installer may write.
    # Source dependencies must be present too, otherwise the staged test imports
    # fail despite a healthy real project.
    for folder in ('Quotation_KEKOREA/contracts', 'Quotation_KEKOREA/agent'):
        source_folder = ROOT / folder
        if source_folder.is_dir():
            for source in source_folder.rglob('*.py'):
                relative = source.relative_to(ROOT)
                target = stage / relative
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    # The old installers are run against a temporary copy. If either fails,
    # nothing in the user's actual project has changed.
    s=(stage/FILES[6]).read_text(encoding='utf-8')
    d=(stage/FILES[7]).read_text(encoding='utf-8')
    clean_ready=('def _verified_contract_seal(' in s
                 and 'def final_document_blockers(' in (stage/FILES[11]).read_text(encoding='utf-8')
                 if (stage/FILES[11]).exists() else False)
    if not clean_ready:
        if (stage/FILES[15]).exists():
            sys.exit('과거 패치 일부만 적용된 상태 같습니다. test_contract_clean_exports.py가 있는데 검증 직인 코드가 없습니다. 파일을 덮어쓰지 않았습니다.')
        cmd=[sys.executable,str(HERE/'step1_clean_exports.py')]
        result=subprocess.run(cmd,cwd=stage,capture_output=True,text=True)
        if result.returncode:
            sys.exit('1단계 수정 검증 실패. 사용자 파일은 변경되지 않았습니다.\n'+result.stdout+'\n'+result.stderr)
    s=(stage/FILES[6]).read_text(encoding='utf-8')
    flow_ready=('contract_direct_draft_' in s and
                '서버 업로드 없이 한 번 클릭' in s)
    if not flow_ready:
        if (stage/FILES[16]).exists():
            sys.exit('과거 패치가 부분 설치된 상태입니다. 기존 test_contract_flow_repair.py를 먼저 확인해 주세요. 사용자 파일을 변경하지 않았습니다.')
        result=subprocess.run([sys.executable,str(HERE/'step2_flow_repair.py')],
                              cwd=stage,capture_output=True,text=True)
        if result.returncode:
            sys.exit('2단계 수정 검증 실패. 사용자 파일은 변경되지 않았습니다.\n'+result.stdout+'\n'+result.stderr)
    module=stage/FILES[12]
    if module.exists():
        old=module.read_text(encoding='utf-8')
        new=(HERE/'latest_instruction.py').read_text(encoding='utf-8')
        if old != new:
            sys.exit('latest_instruction.py가 기존에 다른 내용으로 있습니다. 사용자 파일을 덮어쓰지 않았습니다.')
    else:
        module.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(HERE/'latest_instruction.py',module)
    test=stage/FILES[17]
    if not test.exists():
        test.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(HERE/'test_latest_instruction.py',test)
    else:
        if test.read_text(encoding='utf-8')!=(HERE/'test_latest_instruction.py').read_text(encoding='utf-8'):
            sys.exit('기존 최신 명령 테스트 파일과 내용이 다릅니다. 변경하지 않았습니다.')
    if 'latest_unapplied_request(messages, snapshot)' not in (stage/FILES[6]).read_text(encoding='utf-8'):
        result=subprocess.run([sys.executable,str(HERE/'step3_latest_revision.py')],
                              cwd=stage,capture_output=True,text=True)
        if result.returncode:
            sys.exit('3단계 수정 검증 실패. 사용자 파일은 변경되지 않았습니다.\n'+result.stdout+'\n'+result.stderr)
    # Stage the copy/translation module and tests before mutating real files.
    for target,source in ((FILES[18],'contract_versions.py'),(FILES[19],'test_contract_versions.py')):
        dest=stage/target
        incoming=(HERE/source).read_text(encoding='utf-8')
        if dest.exists() and dest.read_text(encoding='utf-8')!=incoming:
            sys.exit('기존 계약 복사·번역 파일과 충돌합니다. 변경하지 않았습니다: '+target)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(incoming,encoding='utf-8')
    result=subprocess.run([sys.executable,str(HERE/'step4_contract_versions.py')],
                          cwd=stage,capture_output=True,text=True)
    if result.returncode:
        sys.exit('4단계 복사·번역 연결 실패. 사용자 파일 변경 없음.\n'+result.stdout+'\n'+result.stderr)
    note='''\n\n### 2026-11-09 최신 대화 명령과 계약 revision 동기화 (로컬 통합 패치, 배포 미검증)\n- 서명용 계약의 원본은 마지막으로 **승인 후 저장된 revision**이다. 기존 계약서가 있을 때 최근 사용자의 명시적 수정 요청만 현재 revision과 비교한다. 과거 대화 전체의 조건을 뒤섞어 부산/서울 등의 인도장소를 다시 덮어쓰지 않는다.\n- 대화 요청은 즉시 계약서를 변경하지 않는다. 변경값을 확인하고 '선택 후보로 본문 영향 수정안 만들기'→'선택한 변경을 하나의 revision으로 적용'으로 저장한다. 이 승인 후 해시가 revision에 기록되어 페이지를 다시 열어도 이전 명령의 중복 경고를 최소화한다.\n- 페이지를 다시 열었을 때 아직 승인되지 않은 최근 명시적 수정 요청이 있으면 재검토·재적용 기능을 제공한다. 사용자의 직전 발언이 임의로 법적 효력을 가지지 않으며, 저장된 계약 본문과 상충하면 사용자가 비교·승인한다.\n- 기존 DRAFT 직접 다운로드, BOX 2 중복 행 제거, FINAL 직인 인증, PO/PI/CI/PL은 이전 기능 그대로 보존한다. 이 패치에 대한 실제 DB/웹 배포와 전체 회귀 테스트는 별도 검증이 필요하다.\n'''
    for name in FILES[:5]:
        p=stage/name
        text=p.read_text(encoding='utf-8')
        if '### 2026-11-09 최신 대화 명령과 계약 revision 동기화' not in text:
            p.write_text(text+note,encoding='utf-8')
    new_note='''\n\n### 2026-11-09 계약서 동일조건 복사·한국어/영어 전체 번역 (로컬 패치, 배포 미확인)\n- 저장·복사·언어 버전 메뉴의 복사 기능은 마지막 저장된 revision의 거래조건, 당사자, 본문 조항을 새 계약에 복제한다. 원본 계약과 자료는 변경되지 않으며, 원본 계약에 귀속된 참고자료 인용은 복사하지 않는다.\n- 한국어/영어 새 버전 만들기는 사용자가 AI 전송에 명시 동의했을 때 현재 계약 조항과 설명형 조건을 번역하고, 숫자/금액/표준단위/Incoterms 코드 변화가 발생하면 새 계약 생성을 중지한다. 변환 직후 BOX 3에서 본문을 검토·수정할 수 있다.\n- 회사 법인명·품목코드·원본 출처를 추측하거나 변조하지 않는다. 실제 사용/최종 날인 전 양국어 법률 문구를 사용자/전문가가 대조해야 한다. DB 연결/전체 회귀 테스트/운영 배포는 별도 검증 필요.\n'''
    for name in FILES[:5]:
        p=stage/name
        content=p.read_text(encoding='utf-8')
        if '### 2026-11-09 계약서 동일조건 복사·한국어/영어 전체 번역' not in content:
            p.write_text(content+new_note,encoding='utf-8')
    # Validate ALL touched Python code and actual latest instruction tests using
    # only stdlib imports before changing the real repository.
    for name in FILES:
        p=stage/name
        if p.exists() and p.suffix=='.py':
            ast.parse(p.read_text(encoding='utf-8'),filename=name)
    if 'copy_contract(snapshot)' not in (stage/FILES[6]).read_text(encoding='utf-8'):
        sys.exit('계약 복사 UI 연결 확인 실패. 실제 파일 변경 없음.')
    if 'approved_chat_hash' not in (stage/FILES[6]).read_text(encoding='utf-8'):
        sys.exit('승인 해시의 revision 연결 확인에 실패했습니다. 사용자 파일 변경 없음.')
    test_result=subprocess.run(
        [sys.executable,'-m','unittest','Quotation_KEKOREA.tests.test_contract_latest_instruction','Quotation_KEKOREA.tests.test_contract_versions','-v'],
        cwd=stage,capture_output=True,text=True)
    if test_result.returncode:
        sys.exit('최신 수정 명령 단위 테스트 실패. 사용자 파일 변경 없음.\n'+test_result.stdout+'\n'+test_result.stderr)
    changed=[]
    for name in FILES:
        p=stage/name
        if not p.exists():
            continue
        real=ROOT/name
        if not real.exists() or real.read_bytes()!=p.read_bytes():
            changed.append(name)
    backups=ROOT/'local_patch_backups'/('unified_latest_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    for name in changed:
        src=ROOT/name
        if src.exists():
            dest=backups/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,dest)
    for name in changed:
        dest=ROOT/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(stage/name,dest)
    print('OK: 이번 통합 패치 단위 테스트 통과')
    print('변경 파일:',len(changed))
    print('\n'.join(changed))
    print('기존 파일 백업:',backups)
    print('GitHub 반영과 Streamlit 배포는 아직 수행하지 않았습니다.')
