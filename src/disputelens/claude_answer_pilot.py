"""Fixed five-case development pilot; preserve failures and never retry them."""
import argparse
import json
import os
import statistics
from pathlib import Path

from dotenv import load_dotenv

from . import claude_answer_trial
from .build_index import digest
from .embed_batch import write_json


# Fixed before generation. Include a known packing weakness rather than only successes.
CASES = ('E31', 'E33', 'E51', 'E57', 'E58')


def summarize(records):
    completed = [r for r in records if r.get('status') == 'complete_requires_review']
    seconds = [r['generation_seconds'] for r in records if 'generation_seconds' in r]
    return {'case_count': len(records), 'citation_valid_answers': len(completed),
            'failed_or_unavailable': len(records) - len(completed),
            'median_attempt_seconds': statistics.median(seconds) if seconds else None,
            'input_tokens': sum(r.get('usage', {}).get('input_tokens', 0) for r in records),
            'output_tokens': sum(r.get('usage', {}).get('output_tokens', 0) for r in records),
            'semantic_quality': 'not scored; review each answer against source and expected claims'}


def find_saved(case_id, pack_path):
    expected = {'case_id': case_id, 'model': os.getenv('CLAUDE_MODEL'),
                'provider': 'claude', 'context_source': 'focused',
                'context_pack_sha256': digest(pack_path),
                'answer_code_sha256': digest(Path(__file__).with_name('grounded_answer.py')),
                'runner_code_sha256': digest(claude_answer_trial.__file__)}
    matches = []
    for path in Path('data/indexes/answer-trials').glob(case_id + '-claude-*.json'):
        record = json.loads(path.read_text())
        identity = record.get('identity', {})
        if all(identity.get(k) == v for k, v in expected.items()):
            matches.append((path, record))
    if len(matches) > 1:
        raise RuntimeError('Multiple matching attempts; inspect before proceeding.')
    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Make up to five paid requests')
    args = parser.parse_args()
    load_dotenv('.env')
    pointer = json.loads(Path('data/indexes/focused-context/latest.json').read_text())
    directory = Path(pointer['summary_path']).parent
    print('FIXED DEVELOPMENT PILOT: ' + ', '.join(CASES), flush=True)
    print('E31 Adyen flow; E33 provider isolation; E51 Stripe workflow; '
          'E57 clarification; E58 unsupported deadline.', flush=True)
    if not args.run:
        print('No calls made. --run permits up to five paid calls; existing matching attempts are reused.')
        return 0
    if not os.getenv('CLAUDE_MODEL') or not os.getenv('ANTHROPIC_API_KEY'):
        raise RuntimeError('Set Claude model and API key in .env before running.')
    records, rows = [], []
    for case_id in CASES:
        pack_path = directory / 'packs' / (case_id + '.json')
        saved = find_saved(case_id, pack_path)
        reused = saved is not None
        if not saved:
            claude_answer_trial.main(['--dev-case', case_id, '--run'])
            saved = find_saved(case_id, pack_path)
        if saved:
            path, record = saved
        else:
            path, record = None, {'status': 'unavailable'}
        records.append(record)
        coverage = json.loads((directory / 'cases' / (case_id + '.json')).read_text())['focused_context']
        rows.append({'case_id': case_id, 'attempt_path': str(path) if path else None,
                     'reused': reused, 'status': record['status'],
                     'answer_status': record.get('answer', {}).get('status'),
                     'evidence_coverage': coverage,
                     'generation_seconds': record.get('generation_seconds'),
                     'error': record.get('error'), 'semantic_review': 'pending'})
    summary = summarize(records)
    output = directory / 'claude-pilot-summary.json'
    write_json(output, {'summary': summary, 'cases': rows, 'fixed_case_ids': list(CASES),
                        'context_summary_sha256': digest(pointer['summary_path'])})
    print('CITATION-VALID ANSWERS: ' + str(summary['citation_valid_answers']) + '/5')
    print('FAILED OR UNAVAILABLE: ' + str(summary['failed_or_unavailable']))
    print('MEDIAN ATTEMPT SECONDS: ' + str(summary['median_attempt_seconds']))
    print('TOKENS: ' + str(summary['input_tokens']) + ' input; ' + str(summary['output_tokens']) + ' output')
    print('SAVED PILOT: ' + str(output))
    print('Semantic quality pending. Controlled fixtures are separate from real-source cases. '
          'No holdout or GitHub sync.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
