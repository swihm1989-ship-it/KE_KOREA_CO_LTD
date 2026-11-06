"""Update an older contract library integration test for draft-first behavior.

Run from KE_KOREA_CO_LTD repository root. Changes only one test file.
"""
from pathlib import Path
import ast

path = Path('Quotation_KEKOREA/tests/test_contract_library_ui.py')
text = path.read_text(encoding='utf-8')
old_input = "'inspection process'\n).run(timeout=15)"
new_input = "'Please draft a contract with an inspection process'\n).run(timeout=15)"
old_button = "            next(item for item in at.button if item.label == '현재 조건으로 계약서 초안 만들기').click()\n            at.run(timeout=15)\n            self.assertFalse(at.exception)\n"
new_button = "            # An explicit draft request now generates the draft during chat processing.\n            # The manual generate button is intentionally disabled after clauses exist.\n            self.assertTrue(repo.load_contract('contract')[-1]['snapshot']['clauses'])\n"
if old_input not in text:
    raise SystemExit('Expected chat-input text was not found. File unchanged.')
if text.count(old_button) != 1:
    raise SystemExit('Expected manual draft button block not found exactly once. File unchanged.')
updated = text.replace(old_input, new_input, 1).replace(old_button, new_button, 1)
ast.parse(updated, str(path))
path.write_text(updated, encoding='utf-8')
print('Updated only', path)
print('Integration test now explicitly requests auto-drafting and verifies that a draft exists.')
