"""Static packaging assurances to guard deployment boot failure."""
from pathlib import Path
import ast
import unittest
ROOT=Path(__file__).resolve().parents[1]
class PackageStructure(unittest.TestCase):
    def test_all_python_files_parse(self):
        for path in ROOT.rglob('*.py'):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding='utf-8'))
    def test_secrets_not_hard_coded(self):
        gate=(ROOT/'Auth/gate.py').read_text()
        self.assertIn("_setting('KEKOREA_AUTH_PASSWORD')",gate)
        self.assertIn("_setting('KEKOREA_AUTH_SESSION_SECRET')",gate)
        self.assertNotIn("password = '12345'",gate)
        self.assertIn('require_login(root)',gate)
