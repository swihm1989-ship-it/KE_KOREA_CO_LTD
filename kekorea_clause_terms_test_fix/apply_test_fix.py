"""Update one outdated DRAFT test expectation; never touch production source."""
from pathlib import Path
from datetime import datetime
import ast
import shutil

root=Path.cwd()
path=root/'Quotation_KEKOREA/tests/test_contract_workspace_actions.py'
if not path.is_file():
    raise SystemExit('Run this script at the KE_KOREA_CO_LTD repository root.')
s=path.read_text(encoding='utf-8')
old="        self.assertIn('[확인 필요]', text)\n"
new=("        # DRAFT preserves exact sentences; unrelated omissions stay in the appendix.\n"
     "        self.assertIn('첫 번째 계약 문장입니다.', text)\n"
     "        self.assertIn('두 번째 계약 문장입니다.', text)\n"
     "        self.assertNotIn('[확인 필요] 첫 번째 계약 문장입니다.', text)\n"
     "        self.assertNotIn('[확인 필요] 두 번째 계약 문장입니다.', text)\n"
     "        self.assertIn('[필수 확인]', text)\n")
if s.count(old)!=1:
    if new in s: print('Already applied.'); raise SystemExit(0)
    raise SystemExit('Expected test anchor was not found exactly once; no file changed.')
updated=s.replace(old,new,1)
ast.parse(updated)
backup=path.with_suffix(path.suffix+'.backup_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
shutil.copy2(path,backup)
path.write_text(updated,encoding='utf-8')
print('Updated:',path.relative_to(root))
print('Backup:',backup.relative_to(root))
print('Production code unchanged. Re-run full tests to identify the four other failures.')
