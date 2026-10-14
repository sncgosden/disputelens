"""Measure experimental routing on saved E22 evidence; no model or holdout access."""
import json
from pathlib import Path
import hashlib

from .build_index import digest
from .client import ModelError
from .embed_batch import write_json
from .experimental_evidence_routing import route_evidence


def main():
    config_path = Path('eval/experiments/applicability-v1/real-evidence-routing.json')
    config = json.loads(config_path.read_text())
    if digest(config['pack_path']) != config['pack_sha256']:
        raise ModelError('Frozen pack changed.')
    pack = json.loads(Path(config['pack_path']).read_text())
    evidence = [e for g in pack['groups'] for e in g['evidence']]
    for pid, scope in config['scopes'].items():
        item = next((e for e in evidence if e['passage_id'] == pid), None)
        if (item is None or item['headings'] != scope['heading_path']
                or hashlib.sha256(item['text'].encode()).hexdigest() != scope['evidence_text_sha256']):
            raise ModelError('Reviewed evidence mapping mismatch.')
    results = []
    for scenario in config['scenarios']:
        routed = route_evidence(evidence, config['scopes'], scenario['trusted_scope'])
        counts = {k: len(v) for k, v in routed.items()}
        for bucket in ('applicable', 'clarification', 'inapplicable'):
            key = 'expected_mapped_' + bucket
            if key in scenario:
                actual = counts['requires_clarification' if bucket == 'clarification' else bucket]
                if actual != scenario[key]:
                    raise ModelError('Scenario expectation failed: ' + scenario['id'])
        results.append({'scenario': scenario['id'], 'counts': counts,
                        'mapped_decisions': [{'passage_id': row['evidence']['passage_id'],
                                              **row['scope_decision']} for rows in routed.values()
                                             for row in rows if row['evidence']['passage_id'] in config['scopes']]})
        print(scenario['id'] + ': ' + json.dumps(counts))
    path = Path('data/indexes/applicability-trials') / ('real-routing-' + digest(config_path)[:24] + '.json')
    write_json(path, {'config_sha256': digest(config_path), 'runner_sha256': digest(__file__),
                      'pack_sha256': config['pack_sha256'], 'reviewed_passages': len(config['scopes']),
                      'total_passages': len(evidence), 'results': results, 'limitations': config['limitations']})
    print('SAVED: ' + str(path) + '\nOffline only. No pack modified, filtered answer or model call.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
