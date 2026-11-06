"""Import explicitly reviewed local sample manifests without logging originals/keys.

Manifest: [{path,title,contract_types,language,chunks:[{locator,topic,text}]}].
Store manifests and receipts under ignored private/contracts, not source control.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Quotation_KEKOREA.agent.extractor import load_env
from Quotation_KEKOREA.contracts.library import register_sample, publish_sample, read_manifest
from Quotation_KEKOREA.contracts.repository import ContractRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--reindex', action='store_true')
    args = parser.parse_args()
    env = load_env()
    repo = ContractRepository(env)
    entries = json.loads(Path(args.manifest).read_text(encoding='utf-8-sig'))
    if not isinstance(entries, list) or not entries:
        raise ValueError('A nonempty manifest list is required.')
    receipts = []
    for entry in entries:
        path = Path(entry['path'])
        data = path.read_bytes()
        row = register_sample(repo, data, path.name, title=entry['title'],
                              contract_types=entry['contract_types'], language=entry['language'])
        manifest = read_manifest(row)
        wanted = entry.get('chunks') or []
        existing = [{'locator': c.locator, 'topic': c.topic, 'text': c.text} for c in manifest.chunks]
        notices = []
        if wanted and (args.reindex or not manifest.approved or existing != wanted):
            result = publish_sample(repo, row['id'], wanted, env=env)
            row, notices = result['record'], result['notices']
            manifest = read_manifest(row)
        digest = hashlib.sha256(data).hexdigest()
        stored = repo.download_private_file('kekorea-contracts', row['storage_path'])
        if hashlib.sha256(stored).hexdigest() != digest:
            raise ValueError('Final original hash verification failed.')
        receipt = {'id': row['id'], 'title': manifest.title, 'sha256': digest,
                   'original_verified': True, 'approved': manifest.approved,
                   'chunks': len(manifest.chunks), 'vectors': sum(bool(c.embedding) for c in manifest.chunks),
                   'revision': manifest.revision, 'notices': notices}
        receipts.append(receipt)
        print(json.dumps(receipt, ensure_ascii=False))
    output = Path(args.receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
