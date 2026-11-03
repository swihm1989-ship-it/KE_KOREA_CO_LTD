"""Upload one already-reviewed private company record; never print its contacts."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from Quotation_KEKOREA.agent.counterparties import load_local_profiles, upsert_company_profile
from Quotation_KEKOREA.agent.extractor import load_env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--company-key', required=True)
    args = parser.parse_args()
    records = [p for p in load_local_profiles(ROOT / 'private/counterparties/companies.sqlite3')
               if p['company_key'] == args.company_key]
    if len(records) != 1:
        raise SystemExit('No unique private company record was found')
    upsert_company_profile(load_env(), records[0])
    print('Private Supabase company record saved and read-back verified: ' + args.company_key)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None
