"""Inspect one context pack from saved section-scoped hybrid development retrieval."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .context_pack import build_context
from .embed_batch import safe_error, write_json
from .semantic_search import evidence_coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev-case', required=True)
    parser.add_argument('--max-words', type=int, default=6000)
    args = parser.parse_args()
    try:
        config = json.loads(Path('data/pipeline-config.json').read_text())
        cases = json.loads(Path(config['dev_cases_path']).read_text())
        case = next((c for c in cases if c['case_id'] == args.dev_case and c['split'] == 'dev'), None)
        if case is None:
            raise ModelError('Unknown development case; holdout is not loaded.')
        pointer = json.loads(Path('data/indexes/section-scope/hybrid-latest.json').read_text())
        directory = Path(pointer['comparison_path']).parent
        comparison = json.loads(Path(pointer['comparison_path']).read_text())
        saved_path = directory / 'cases' / (case['case_id'] + '.json')
        saved = json.loads(saved_path.read_text())
        identity = saved['identity']
        if (comparison['status'] != 'complete' or saved['identity'] != comparison['identity']
                or identity['strategy'] != 'hybrid'
                or identity['dev_cases_sha256'] != digest(config['dev_cases_path'])
                or identity['embedding_units_sha256'] != digest(config['embedding_units_path'])
                or identity['code_sha256']['section_scope.py'] != digest(Path(__file__).with_name('section_scope.py'))
                or saved['question'] != case['question'] or saved['filters'] != case['filters']):
            raise ModelError('Saved scoped retrieval does not match current inputs and guards.')
        scopes = json.loads((directory / 'passage-scope-map.json').read_text())
        if scopes['identity'] != identity:
            raise ModelError('Scope-map configuration mismatch.')
        units = json.loads(Path(config['embedding_units_path']).read_text())['chunks']
        by_id = {u['chunk_id']: u for u in units}
        if any(by_id.get(r['unit']['chunk_id']) != r['unit'] for r in saved['results']):
            raise ModelError('Saved candidate payload differs from original search units.')
        # Construction sees no expected evidence or answer fields.
        pack = build_context(saved['results'], saved['filters'], scopes['passages'], args.max_words)
        pack['question'] = saved['question']
        pack['identity'] = {'saved_retrieval_sha256': digest(saved_path),
                            'scope_map_sha256': digest(directory / 'passage-scope-map.json'),
                            'builder_code_sha256': digest(Path(__file__).with_name('context_pack.py')),
                            'max_words': args.max_words}
        # Inspect expected-evidence coverage only AFTER constructing the pack.
        context_results = [{'rank': n, 'unit': {'passage_ids': [e['passage_id'] for e in g['evidence']],
                                               'evidence': g['evidence']}}
                           for n, g in enumerate(pack['groups'], 1)]
        pack['development_evidence_coverage'] = evidence_coverage(
            context_results, case['relevant_passage_ids'], units)
        run_id = hashlib.sha256(json.dumps(pack['identity'], sort_keys=True).encode()).hexdigest()[:24]
        output = Path('data/indexes/context-packs') / (case['case_id'] + '-' + run_id)
        write_json(output / 'pack.json', pack)
        (output / 'context.txt').write_text(pack['text'] + '\n', encoding='utf-8')
        print(f'PACK: {pack["included_units"]}/{pack["input_units"]} retrieved units; '
              f'{len(pack["groups"])} groups; {len(pack["citations"])} citation labels.')
        print(f'WORD BUDGET: {pack["budget"]["used"]}/{args.max_words}; '
              f'groups omitted: {len(pack["omitted_groups"])}.')
        for entry in pack['development_evidence_coverage']:
            print(f'EVIDENCE: {entry["passage_id"]}: '
                  f'{entry["covered_characters"]}/{entry["total_characters"]} characters retained.')
        print(f'SAVED: {output / "context.txt"}\nSAVED: {output / "pack.json"}')
        print('Word budget is not a model-token check. No answer generated. '
              'No model calls, holdout, index changes or GitHub sync.')
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
