"""Offline reviewed-span routing report; no production integration or model calls."""
import hashlib
import json
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .embed_batch import write_json
from .experimental_applicability import decide_applicability

CONFIG = Path('eval/experiments/applicability-v1/reviewed-slice-map.json')


def load_slice():
    config = json.loads(CONFIG.read_text())
    if digest(config['inventory_path']) != config['inventory_sha256']:
        raise ModelError('Inventory changed.')
    inventory = json.loads(Path(config['inventory_path']).read_text())
    originals = {p['passage_id']: p for p in inventory['passages']}
    if len(config['maps']) != len(originals) or {m['passage_id'] for m in config['maps']} != set(originals):
        raise ModelError('Mapping disposition coverage incomplete.')
    if len({m['passage_id'] for m in config['maps']}) != len(config['maps']):
        raise ModelError('Duplicate mapping.')
    for m in config['maps']:
        for occurrence in originals[m['passage_id']]['occurrences']:
            for e in occurrence['evidence']:
                if (hashlib.sha256(e['text'].encode()).hexdigest() != m['text_sha256']
                        or e['headings'] != m['heading_path']
                        or not 0 <= m['span_start'] < m['span_end'] <= len(e['text'])):
                    raise ModelError('Source mapping provenance/span mismatch.')
    for path, expected in inventory['input_hashes'].items():
        if digest(path) != expected:
            raise ModelError('Saved inventory input changed.')
    return config, originals


def main():
    config, originals = load_slice()
    results = []
    for m in config['maps']:
        item = originals[m['passage_id']]
        scenarios = []
        for occurrence in item['occurrences']:
            pack = json.loads(Path(occurrence['pack_path']).read_text())
            trusted = {k:v for k,v in pack['trusted_settings'].items() if k != 'corpus'}
            scenarios.append({'case_id': occurrence['case_id'], 'scope_origin': 'original_structured',
                              **decide_applicability(m, trusted)})
        matched = decide_applicability(m, m['requirements'])
        scenarios.append({'scope_origin': 'simulated_matching', **matched})
        e=item['occurrences'][0]['evidence'][0]
        results.append({'passage_id':m['passage_id'], 'disposition':m['disposition'],
                        'span_text':e['text'][m['span_start']:m['span_end']],
                        'locator':e['locator'], 'source_character_start':e['character_start']+m['span_start'],
                        'source_character_end':e['character_start']+m['span_end'], 'scenarios':scenarios})
    reviewed=sum(m['review_status']=='reviewed' for m in config['maps'])
    pending=len(results)-reviewed
    summary={'total':len(results),'dispositions_recorded':len(results),'reviewed':reviewed,
             'quarantined':pending,'independent_review':False,'promotion':'blocked_remaining_gates'}
    out=Path('data/indexes/applicability-trials')/('slice-'+digest(CONFIG)[:24]+'.json')
    write_json(out, {'config_sha256':digest(CONFIG),'runner_sha256':digest(__file__),
                     'summary':summary,'results':results,'remaining_gates':config['remaining_gates']})
    print(json.dumps(summary))
    print('SAVED: '+str(out)+'\nNo model calls, filtered production packs or holdout access.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
