# Apply files rebuilt from the user's own 4-file ZIP; no fragile anchors.
from pathlib import Path
from datetime import datetime
from hashlib import sha256
import json, shutil, ast, sys, tempfile

HERE=Path(__file__).resolve().parent
PAYLOAD=HERE/'payload'
ROOT=HERE.parent
MANIFEST=json.loads((PAYLOAD/'MANIFEST.json').read_text(encoding='utf-8'))

SOURCE_FILES=MANIFEST['source']
README_FILES=[
 'README.md',
 'Quotation_KEKOREA/README.md',
 'Quotation_KEKOREA/README_CONTRACTS.md',
 'Quotation_KEKOREA/Team/README.md',
 'Quotation_KEKOREA/Presentation/README.md',
]
README_NOTE='''\n## Auth and contract review integration (2026-11-09)\n\n- Auth/gate.py protects the entire Streamlit UI before sidebar, database and AI use. Streamlit Secrets configure one admin login; a signed cookie expires 12 hours after initial login, even across refresh.\n- Auth/session.py provides HMAC-signed time-limited tokens. The CookieController is a JavaScript-cookie component (not HttpOnly), appropriate only for a limited demo; production access needs stronger authentication and rate limiting.\n- BOX 3 AI review issue objects and text issues normalize into explicit unconfirmed review items. Unknown AI issue structures fail safely without changing existing contract text or notes.\n- Proposed revisions require human comparison/approval and atomic revision saving. The UI provides the full approved preview and displays all remaining FINAL blockers.\n- Logged-in admin no longer retypes the FINAL seal password. Direct standalone contract module retains a legacy password fallback for compatibility; explicit final approval and verified seal still apply.\n- Dependencies: streamlit-cookies-controller==0.0.4. Credentials and session signing secret belong in private Streamlit Secrets, never in Git.\n- The uploaded four Python files were the direct source for this repair, rather than a historical GitHub or ZIP patch version.\n'''

def digest(path): return sha256(path.read_bytes()).hexdigest()

def main():
    # Preflight ALL inputs. A mismatch means there are newer user changes; do not overwrite.
    paths={}
    for rel, expected in SOURCE_FILES.items():
        target=ROOT/rel
        if not target.is_file():
            raise RuntimeError(f'원본 파일 누락: {rel}')
        actual=digest(target)
        final=MANIFEST['output'][rel]
        if actual not in {expected,final}:
            raise RuntimeError(f'업로드 뒤 코드가 추가 수정됐습니다: {rel}. 이 파일을 덮어쓰지 않았습니다. 최신 소스로 다시 생성해야 합니다.')
        paths[rel]=target
    for rel in README_FILES:
        if not (ROOT/rel).is_file(): raise RuntimeError(f'필수 README 누락: {rel}')
    requirement=ROOT/'Quotation_KEKOREA/requirements.txt'
    if not requirement.is_file(): raise RuntimeError('requirements.txt 누락')
    # Validate shipped payload and all Python syntax before backup/changes.
    for rel, expected in MANIFEST['output'].items():
        src=PAYLOAD/rel
        if digest(src)!=expected: raise RuntimeError(f'패키지 파일 검증 실패: {rel}')
        ast.parse(src.read_text(encoding='utf-8'),filename=str(src))
    # Staging of all final file bytes before any writes.
    updates={}
    for rel in MANIFEST['output']:
        dst=ROOT/rel
        if not dst.exists() or digest(dst)!=MANIFEST['output'][rel]: updates[rel]=(PAYLOAD/rel).read_bytes()
    for rel in README_FILES:
        old=(ROOT/rel).read_text(encoding='utf-8-sig')
        if '## Auth and contract review integration (2026-11-09)' not in old:
            updates[rel]=(old.rstrip()+'\n\n'+README_NOTE.strip()+'\n').encode('utf-8')
    old=requirement.read_text(encoding='utf-8-sig')
    if 'streamlit-cookies-controller' not in old:
        updates['Quotation_KEKOREA/requirements.txt']=(old.rstrip()+'\nstreamlit-cookies-controller==0.0.4\n').encode('utf-8')
    if not updates:
        print('이미 설치됨: 변경사항이 없습니다.');return
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    backup=ROOT/'local_patch_backups'/f'auth_actual_source_{stamp}'
    backups=[]
    try:
        for rel in updates:
            target=ROOT/rel
            if target.is_file():
                b=backup/rel;b.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(target,b);backups.append(rel)
        # Fresh whole-file replacements: not string replacements against user's working copy.
        for rel,body in updates.items():
            target=ROOT/rel;target.parent.mkdir(parents=True,exist_ok=True)
            tmp=target.with_name(target.name+'.kekorea.tmp')
            tmp.write_bytes(body)
            tmp.replace(target)
    except Exception:
        for rel in reversed(updates):
            target=ROOT/rel
            if rel in backups: shutil.copy2(backup/rel,target)
            elif target.exists(): target.unlink()
        raise
    print('설치 성공. 변경 파일:',len(updates))
    for rel in updates:print(' ',rel)
    print('백업:',backup)
    print('GitHub와 Streamlit 배포는 자동 수행하지 않았습니다.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('설치 중단 — 원본을 무조건 덮어쓰지 않습니다:',exc)
        sys.exit(1)
