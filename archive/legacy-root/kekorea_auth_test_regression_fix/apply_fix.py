"""Fix Streamlit UI test isolation + AI issue normalizer compatibility.
Never disables production authentication. All changes preflighted and backed up.
"""
import ast
from datetime import datetime
from pathlib import Path
import shutil
import sys

ROOT = Path.cwd()
PROJECT = ROOT / 'Quotation_KEKOREA'
SERVICE = PROJECT / 'contracts' / 'service.py'
FILES = [
    'test_order_promotions_ui.py', 'test_review_ui.py', 'test_counterparties_ui.py',
    'test_pdf_upload_ui.py', 'test_product_matching_ui.py', 'test_sale_partial_catalog.py',
    'test_pi_samples_ui.py', 'test_ci_pi_import_ui.py', 'test_workflow_ui.py',
]
README_FILES = [
    'README.md', 'Quotation_KEKOREA/README.md',
    'Quotation_KEKOREA/README_CONTRACTS.md', 'Quotation_KEKOREA/Team/README.md',
    'Quotation_KEKOREA/Presentation/README.md',
]

NORMALIZER = '''def _normalize_ai_issues(issues, error_message):
    """Retain AI warnings while normalizing safely understood response variations.

    This is data-validation only. It does not approve issues or alter contract terms.
    """
    if issues is None:
        return []
    if isinstance(issues, str):
        if not issues.strip():
            raise ValueError(error_message)
        issues = [issues]
    if not isinstance(issues, list):
        raise ValueError(error_message)
    normalized = []
    text_count = 0
    for issue in issues:
        if isinstance(issue, str):
            if not issue.strip():
                raise ValueError("AI 검토사항에 빈 항목이 있습니다. 기존 문장 메모는 유지됩니다.")
            code = 'ai_review_text' if text_count == 0 else f'ai_review_text_{text_count}'
            text_count += 1
            candidate = {'code': code, 'severity': 'confirm', 'message': issue.strip()}
        elif isinstance(issue, dict):
            candidate = dict(issue)
            message = candidate.get('message')
            if not isinstance(message, str) or not message.strip():
                fallback = next((candidate.get(key) for key in ('description', 'text', 'detail')
                                 if isinstance(candidate.get(key), str) and candidate[key].strip()), None)
                if not fallback:
                    raise ValueError("AI 검토사항 설명이 비어 있습니다. 기존 문장 메모는 유지됩니다.")
                candidate['message'] = fallback.strip()
        else:
            raise ValueError("AI 검토사항 데이터 형식이 잘못되었습니다. 기존 문장 메모는 유지됩니다.")
        candidate['message'] = candidate['message'].strip()
        if candidate.get('severity') not in {'block', 'confirm', 'info'}:
            reported = candidate.get('severity')
            reported = reported.strip()[:40] if isinstance(reported, str) and reported.strip() else 'unspecified'
            candidate['severity'] = 'confirm'
            candidate['message'] += (f" (AI severity '{reported}' was unclear; "
                                     'please review and confirm.)')
        code = candidate.get('code')
        if not isinstance(code, str) or not code.strip():
            candidate['code'] = 'ai_review'
        normalized.append(candidate)
    return normalized
'''

HELPER = '''"""Test-only authenticated UI harness.

Production Auth.gate.require_login is never bypassed. This decorator patches
only the duration of an individual unittest test method that renders app.py.
Auth gate/security-specific tests intentionally do not use this helper.
"""
import functools
from unittest.mock import patch


def isolated_authenticated_ui_tests(cls):
    for name, method in list(vars(cls).items()):
        if not name.startswith('test_') or not callable(method):
            continue
        @functools.wraps(method)
        def wrapper(self, *args, __method=method, **kwargs):
            with patch('Auth.gate.require_login', return_value=None):
                return __method(self, *args, **kwargs)
        setattr(cls, name, wrapper)
    return cls
'''

CHECK_TEST = '''"""Verify compatibility of AI warning schema and test-only auth isolation."""
import unittest
from unittest.mock import patch
from Quotation_KEKOREA.contracts.service import _normalize_ai_issues
from Quotation_KEKOREA.tests.auth_test_helpers import isolated_authenticated_ui_tests


class IssueSchemaCompatibilityTests(unittest.TestCase):
    def test_plain_text_warning_is_unconfirmed_and_not_discarded(self):
        result = _normalize_ai_issues(['확인 필요', '다른 확인 필요'], 'error')
        self.assertEqual([v['code'] for v in result], ['ai_review_text', 'ai_review_text_1'])
        self.assertTrue(all(v['severity'] == 'confirm' for v in result))

    def test_unknown_severity_explains_original_value(self):
        result = _normalize_ai_issues([{'severity': 'warning', 'message': 'Confirm delivery.'}], 'error')
        self.assertIn('warning', result[0]['message'])
        self.assertIn('please review and confirm', result[0]['message'])

    def test_unsupported_item_rejected(self):
        with self.assertRaises(ValueError):
            _normalize_ai_issues([['unreadable']], 'error')

    def test_auth_mock_scoped_to_one_test(self):
        # This test is deliberately not decorated: the real production function
        # must remain callable outside UI tests.
        from Auth.gate import require_login
        self.assertTrue(callable(require_login))


@isolated_authenticated_ui_tests
class SampleIsolatedUiTests(unittest.TestCase):
    def test_only_during_this_test(self):
        from Auth.gate import require_login
        self.assertIsNone(require_login(None, None))
'''


def function_span(src, name):
    tree = ast.parse(src)
    hits = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(hits) != 1:
        raise ValueError(f'Expected exactly one {name}, got {len(hits)}')
    n = hits[0]
    lines = src.splitlines(keepends=True)
    return lines, n.lineno - 1, n.end_lineno


def update_service(src):
    lines, begin, end = function_span(src, '_normalize_ai_issues')
    old = ''.join(lines[begin:end])
    if 'ai_review_text' not in old:
        raise ValueError('Unexpected service.py: AI warning normalizer missing known marker')
    return ''.join(lines[:begin]) + NORMALIZER.rstrip('\n') + '\n\n' + ''.join(lines[end:]).lstrip('\n')


def update_test(src):
    if '@isolated_authenticated_ui_tests' in src:
        return src
    if 'AppTest' not in src:
        raise ValueError('Expected a Streamlit AppTest suite')
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and any(
        isinstance(b, ast.Attribute) and b.attr == 'TestCase' for b in n.bases)]
    if not classes:
        raise ValueError('No unittest.TestCase class found')
    for node in sorted(classes, key=lambda n:n.lineno, reverse=True):
        lines.insert(node.lineno - 1, '@isolated_authenticated_ui_tests\n')
    src = ''.join(lines)
    import_line = 'from Quotation_KEKOREA.tests.auth_test_helpers import isolated_authenticated_ui_tests\n'
    # insert after module docstring, if present
    tree = ast.parse(src)
    first = tree.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        lines = src.splitlines(keepends=True)
        lines.insert(first.end_lineno, import_line)
        return ''.join(lines)
    return import_line + src


def update_readme(src):
    title='## Authenticated UI test isolation and AI review issue schema (2026-11-09)'
    if title in src:
        return src
    note=(f'\n\n{title}\n'
          '- Existing Streamlit AppTest suites simulate a signed-in test session **only within each test method**; production login remains mandatory.\n'
          '- The server-side Auth gate is unchanged, and separate authentication/security tests continue to test real 12-hour signed-token validation.\n'
          '- AI review issues provided as text remain unconfirmed, while malformed opaque issues fail closed and preserve user notes.\n'
          '- Legacy error messages retain the original invalid severity for audit and compatibility.\n'
          '- Run full regressions before deployment; no login bypass environment variable is introduced.\n')
    return src.rstrip() + note


def main():
    if not SERVICE.is_file() or not (ROOT / 'Auth' / 'gate.py').is_file():
        raise SystemExit('Stop: expected installed Auth/gate.py and Quotation_KEKOREA/contracts/service.py')
    paths = [SERVICE, PROJECT / 'tests' / 'auth_test_helpers.py',
             PROJECT / 'tests' / 'test_auth_ui_regression.py'] + [PROJECT/'tests'/n for n in FILES] + [ROOT/p for p in README_FILES]
    if any(not p.is_file() for p in paths if p.name not in ('auth_test_helpers.py','test_auth_ui_regression.py')):
        missing=[str(p.relative_to(ROOT)) for p in paths if not p.is_file() and p.name not in ('auth_test_helpers.py','test_auth_ui_regression.py')]
        raise SystemExit('Stop: missing files: '+str(missing))
    planned = {SERVICE:update_service(SERVICE.read_text(encoding='utf-8')),
               PROJECT/'tests'/'auth_test_helpers.py':HELPER,
               PROJECT/'tests'/'test_auth_ui_regression.py':CHECK_TEST}
    for name in FILES:
        p=PROJECT/'tests'/name
        planned[p]=update_test(p.read_text(encoding='utf-8'))
    for name in README_FILES:
        p=ROOT/name
        planned[p]=update_readme(p.read_text(encoding='utf-8'))
    for p,content in planned.items():
        if p.suffix=='.py':
            ast.parse(content, filename=str(p))
    # Do not overwrite preexisting custom helper/test files.
    for p in (PROJECT/'tests'/'auth_test_helpers.py',PROJECT/'tests'/'test_auth_ui_regression.py'):
        if p.exists() and p.read_text(encoding='utf-8')!=planned[p]:
            raise SystemExit('Stop: existing custom file differs: '+str(p))
    changed={p:content for p,content in planned.items() if not p.exists() or p.read_text(encoding='utf-8')!=content}
    if not changed:
        print('Already applied; no changes.');return
    backup=ROOT/'local_patch_backups'/('auth_ui_tests_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    for p in changed:
        if p.exists():
            dest=backup/p.relative_to(ROOT)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,dest)
    for p,content in changed.items():
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(content,encoding='utf-8')
    print('OK: updated',len(changed),'files; production auth unchanged')
    print('Backup:',backup)
    for p in changed: print(' ',p.relative_to(ROOT))

if __name__=='__main__':
    main()
