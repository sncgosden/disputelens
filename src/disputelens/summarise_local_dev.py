"""Offline summary of saved local development attempts for one model. No model calls."""
import argparse
import json
from collections import Counter
from pathlib import Path

from .local_dev_batch import TRIALS, dev_case_ids, MODELS


def summarise(model, case_ids, directory=TRIALS):
    rows = {}
    for path in Path(directory).glob('*.json'):
        try:
            record = json.loads(path.read_text())
        except ValueError:
            continue
        identity = record.get('identity') or {}
        if (identity.get('model') != model or identity.get('context_source') != 'full'
                or identity.get('max_tokens') != 8192 or record.get('status') not in
                ('complete_requires_review', 'failed', 'started')):
            continue
        answer = record.get('answer') or {}
        error = record.get('error') or ''
        rows[identity['case_id']] = {
            'case_id': identity['case_id'], 'status': record['status'],
            'seconds': round(record.get('generation_seconds') or 0, 1),
            'answer_status': answer.get('status'), 'claims': len(answer.get('claims', [])),
            'error': error[:160], 'file': path.name}
    for case in case_ids:
        rows.setdefault(case, {'case_id': case, 'status': 'not_attempted', 'seconds': 0,
                               'answer_status': None, 'claims': 0, 'error': '', 'file': None})
    ordered = [rows[c] for c in case_ids]
    done = [r for r in ordered if r['status'] == 'complete_requires_review']
    times = sorted(r['seconds'] for r in done)
    counts = Counter(r['status'] for r in ordered)
    return {'model': model, 'cases': len(case_ids), 'status_counts': dict(counts),
            'answer_status_counts': dict(Counter(r['answer_status'] for r in done)),
            'median_seconds_complete': times[len(times) // 2] if times else None,
            'max_seconds_complete': times[-1] if times else None,
            'limits': ['Structural validation only (citation IDs and quotes); semantic correctness not assessed',
                       'Single sample per case; development cases only; holdout untouched',
                       'Not comparable with Claude results without semantic review'],
            'rows': ordered}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, choices=MODELS)
    args = parser.parse_args()
    config = json.loads(Path('data/pipeline-config.json').read_text())
    ids = dev_case_ids(json.loads(Path(config['dev_cases_path']).read_text()))
    result = summarise(args.model, ids)
    out = Path('data/indexes/local-dev-summary')
    out.mkdir(parents=True, exist_ok=True)
    path = out / (args.model + '.json')
    path.write_text(json.dumps(result, indent=2))
    print(f"{args.model}: {result['status_counts']}; answer statuses {result['answer_status_counts']}")
    print(f"median {result['median_seconds_complete']}s, max {result['max_seconds_complete']}s (completed answers)")
    for r in result['rows']:
        if r['status'] != 'complete_requires_review':
            print(f"  {r['case_id']}: {r['status']} {r['seconds']}s {r['error']}")
    print('SAVED: ' + str(path))


if __name__ == '__main__':
    main()
