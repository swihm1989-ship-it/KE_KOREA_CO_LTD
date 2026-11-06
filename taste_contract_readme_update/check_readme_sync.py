"""Fail staged application-code commits that omit any of the five maintained READMEs.

Local git hook guard. Only verifies staged file names, not semantic document quality.
"""
from __future__ import annotations

import subprocess
import sys

READMES = {
    'README.md',
    'Quotation_KEKOREA/README.md',
    'Quotation_KEKOREA/README_CONTRACTS.md',
    'Quotation_KEKOREA/Team/README.md',
    'Quotation_KEKOREA/Presentation/README.md',
}


def requires_docs(path: str) -> bool:
    if not path.startswith('Quotation_KEKOREA/'):
        return False
    if '/tests/' in path or path.endswith('/AGENTS.md') or path in READMES:
        return False
    return path.endswith(('.py', '.sql', '.toml', '.yaml', '.yml', '.txt'))


def missing_docs(staged: set[str]) -> list[str]:
    if not any(requires_docs(path) for path in staged):
        return []
    return sorted(READMES - staged)


def main() -> int:
    proc = subprocess.run(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACDMR'],
                          capture_output=True, text=True)
    if proc.returncode:
        print('README guard could not read staged git changes:', proc.stderr, file=sys.stderr)
        return 2
    files = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    missing = missing_docs(files)
    if not missing:
        print('README sync guard: OK')
        return 0
    print('README sync guard: application code changed, but 5-README synchronization is incomplete.', file=sys.stderr)
    for path in missing:
        print('  missing:', path, file=sys.stderr)
    print('Review/update each README, then stage all five. Do not insert meaningless edits to bypass review.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
