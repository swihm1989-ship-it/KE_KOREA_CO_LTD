"""Correct the wrong risk number in the new Streamlit regression test only.

No production code or README files are changed.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / 'Quotation_KEKOREA' / 'tests' / 'test_contract_risk_review_v2.py'

OLD = """        # Page 2 includes risk #6, targeting s2. Select #7, targeting s1.
        self.at.button(key='risk_pick_sample_1_7').click()
"""
NEW = """        # Page 2 includes risk #6 (index 5), which targets s1.
        # Risk #7 (index 6) targets s2, so selecting #7 cannot render the s1 editor.
        self.at.button(key='risk_pick_sample_1_6').click()
"""

def main():
    if not TARGET.is_file():
        raise SystemExit(f'ERROR: Cannot find test: {TARGET}')
    content = TARGET.read_text(encoding='utf-8')
    if NEW in content:
        print('Already fixed; no changes made.')
        return
    if content.count(OLD) != 1:
        raise SystemExit('ERROR: Test file differs from expected v2 version; refusing modification.')
    updated = content.replace(OLD, NEW, 1)
    assert "self.at.text_area(key='risk_edited_sample_1_s1')" in updated
    compile(updated, str(TARGET), 'exec')
    backup = TARGET.with_suffix('.py.before_risk_test_fix.bak')
    if not backup.exists():
        shutil.copy2(TARGET, backup)
    TARGET.write_text(updated, encoding='utf-8')
    print('Fixed the test selection: risk #6 -> s1. Production code unchanged.')
    print(f'Backup: {backup}')

if __name__ == '__main__':
    main()
