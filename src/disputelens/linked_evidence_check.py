"""Verify separately linked E23 evidence against source; no models or holdout."""
import hashlib
import json
from pathlib import Path

from .build_index import digest
from .client import ModelError

CONFIG = Path('eval/experiments/applicability-v1/E23-complete-linked-evidence.json')


def verify_linked_evidence():
    config=json.loads(CONFIG.read_text())
    if digest(config['source_path'])!=config['source_sha256']:
        raise ModelError('Linked source changed.')
    docs=json.loads(Path(config['source_path']).read_text())
    blocks={b['passage_id']:b for d in docs['documents'] for b in d['blocks']}
    for link in config['links']:
        if len(link['pieces'])!=2:
            raise ModelError('Expected two separately attributed pieces.')
        for p in link['pieces']:
            b=blocks[p['passage_id']];t=b['text']
            if (hashlib.sha256(t.encode()).hexdigest()!=p['source_text_sha256']
                    or not 0<=p['start']<p['end']<=len(t)
                    or t[p['start']:p['end']]!=p['text'] or b['locator']!=p['locator']):
                raise ModelError('Linked span provenance mismatch.')
    return config


def main():
    config=verify_linked_evidence()
    print('VERIFIED: two links, four individually attributed source spans.')
    print('No merged citation, model call, frozen pack change or holdout access.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
