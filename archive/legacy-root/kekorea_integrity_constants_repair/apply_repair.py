"""Repair module-scope constants omitted by the prior integrity patch installer.
Run from KE_KOREA_CO_LTD repository root. Never change contract data.
"""
from __future__ import annotations
import ast
from datetime import datetime
from pathlib import Path
import re
import shutil

root = Path.cwd()
target = root / 'Quotation_KEKOREA' / 'contracts' / 'normalize_terms.py'
if not target.is_file():
    raise SystemExit('ERROR: run from KE_KOREA_CO_LTD repository root (normalize_terms.py missing).')
source = target.read_text(encoding='utf-8')
module = ast.parse(source, filename=str(target))
assigned = set()
for stmt in module.body:
    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        nodes = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
        for node in nodes:
            if isinstance(node, ast.Name): assigned.add(node.id)
constants = {
    '_INCOTERMS': "_INCOTERMS = re.compile(r'(?<![A-Z])(?:EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)(?![A-Z])', re.I)",
    '_SCHEDULE': "_SCHEDULE = re.compile(r'일정|납기|지연|통지|협의|인수|schedule|delay|notice|notify|coordinate|agree.*date|jadwal|keterlambatan|pemberitahuan', re.I)",
    '_NUM': "_NUM = re.compile(r'(?<!\\w)(-?\\d[\\d,]*(?:\\.\\d+)?)(?!\\w)')",
    '_UNIT': "_UNIT = re.compile(r'(?i)(?:/|per\\s+|당\\s*)(kg|kgs|kilogram|kilograms|mt|metric\\s+tons?|tonne?s?|pcs?|units?|wp|watts?)\\b')",
}
missing = [name for name in constants if name not in assigned]
if missing:
    if not re.search(r'^def _extract_incoterm\(', source, flags=re.M):
        raise SystemExit('ERROR: unexpected module layout. No changes made; inspect normalize_terms.py.')
    block = '\n'.join(constants[name] for name in missing) + '\n\n'
    updated = source.replace('def _extract_incoterm(', block + 'def _extract_incoterm(', 1)
else:
    updated = source
ast.parse(updated, filename=str(target))
# Catch missing/malformed regex definitions before making changes.
ns = {'re': re}
for name in constants:
    existing = next((x for x in ast.parse(updated).body if isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in x.targets)), None)
    if existing is None:
        raise SystemExit(f'ERROR: {name} is undefined at module scope')
    exec(compile(ast.Module(body=[existing], type_ignores=[]), str(target), 'exec'), ns)
    if not isinstance(ns[name], type(re.compile(''))):
        raise SystemExit(f'ERROR: {name} is not a compiled regex')
if ns['_NUM'].search('5,000').lastindex is None:
    raise SystemExit('ERROR: _NUM must contain capturing group 1. Fix before rerunning.')
if ns['_UNIT'].search('USD 5/KG') is None or ns['_INCOTERMS'].search('EXW Busan') is None:
    raise SystemExit('ERROR: expected regex sample match failed.')
if updated == source:
    print('No missing constants. All four module-level regular expressions pass checks.')
else:
    backup = target.with_name('normalize_terms.py.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(target, backup)
    target.write_text(updated, encoding='utf-8')
    print('Repaired:', ', '.join(missing))
    print('Backup:', backup)
print('Next: run the 8 integrity tests, then full regression suite. Do not push until both pass.')
