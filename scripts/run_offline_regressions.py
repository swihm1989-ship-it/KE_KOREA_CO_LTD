"""Run the real unittest suites with external network connections prohibited.

Install before application modules bind default HTTP openers. Fake providers
remain usable. This protects private local fixtures and prevents accidental
paid provider calls during regression tests. No test is skipped or weakened.
"""
import os
import argparse
from pathlib import Path
import socket
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def blocked_connect(self, address):
    raise OSError('Offline regression suite: network connections disabled')


def main():
    socket.socket.connect = blocked_connect
    socket.socket.connect_ex = blocked_connect
    # Credentials are unnecessary for the suite: use only explicit test configs.
    for key in tuple(os.environ):
        if key.startswith(('OPENAI_', 'SUPABASE_', 'NEWS_SUPABASE_', 'WHOIS_')):
            os.environ.pop(key, None)
    os.chdir(ROOT)
    parser=argparse.ArgumentParser()
    parser.add_argument('--pattern',default='test*.py')
    parser.add_argument('targets',nargs='*')
    args=parser.parse_args()
    targets = args.targets or ['Quotation_KEKOREA/tests', 'Quotation_KEKOREA/orchestration/tests']
    if len(targets)>1:
        # Existing suites contain identically named modules and use different
        # import roots. Separate processes preserve the repository's discovery.
        codes=[subprocess.run([sys.executable, str(Path(__file__).resolve()),
                               '--pattern',args.pattern,target]).returncode for target in targets]
        return 0 if all(code==0 for code in codes) else 1
    suite = unittest.TestSuite()
    for target in targets:
        suite.addTests(unittest.TestLoader().discover(target, pattern=args.pattern))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
