"""Offline minimal contract regression for the patch itself."""
from pathlib import Path
import tempfile
import subprocess
import sys

SRC = Path(__file__).with_name('apply_first_option_fix.py')
for_base = Path('Quotation_KEKOREA/contracts/risk_review_ui.py')
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    dest = root / for_base
    dest.parent.mkdir(parents=True)
    dest.write_text("def example(st, picked, contract_id, revision, sentence_id, index):\n    " +
      "if st.button('이 추천안 선택', key=f'risk_choose_{contract_id}_{revision}_{sentence_id}_{index}',\n                              disabled=picked):\n        return True\n", encoding='utf-8')
    for p in ['README.md','Quotation_KEKOREA/README.md','Quotation_KEKOREA/README_CONTRACTS.md','Quotation_KEKOREA/Team/README.md','Quotation_KEKOREA/Presentation/README.md']:
        f=root/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('# Existing Docs\n',encoding='utf-8')
    first=subprocess.run([sys.executable,str(SRC)],cwd=root,capture_output=True,text=True)
    assert first.returncode==0,first.stderr+first.stdout
    assert "type='primary' if picked else 'secondary'" in dest.read_text(encoding='utf-8')
    assert 'disabled=picked' not in dest.read_text(encoding='utf-8')
    second=subprocess.run([sys.executable,str(SRC)],cwd=root,capture_output=True,text=True)
    assert second.returncode==0,second.stderr+second.stdout
    assert '중복 적용' in second.stdout
    print('PATCH TESTS OK')
