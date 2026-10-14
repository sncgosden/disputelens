"""User-run local development batch: one model, all 45 development cases, sequential.

Policy: reuse any saved attempt with identical settings (complete or failed), never retry,
record failures as results and continue, stop after three consecutive failures or when the
model is not loaded. Development cases only; the holdout split is never read.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from .client import ModelError

TRIALS = Path('data/indexes/answer-trials')
MODELS = ('qwen3.5-4b', 'qwen3.5-9b-mlx')
MAX_CONSECUTIVE_FAILURES = 3


def dev_case_ids(cases):
    return [c['case_id'] for c in cases if c.get('split') == 'dev']


def saved_attempts(model, directory=TRIALS, reasoning='server default', timeout=300):
    """Map case_id -> status for attempts made with the standard full-context settings."""
    found = {}
    for path in Path(directory).glob('*.json'):
        try:
            record = json.loads(path.read_text())
        except ValueError:
            continue
        identity = record.get('identity') or {}
        if (identity.get('model') == model and identity.get('context_source') == 'full'
                and identity.get('max_tokens') == 8192 and identity.get('reasoning', 'server default') == reasoning
                and identity.get('timeout_seconds', 300) == timeout
                and record.get('status') in
                ('complete_requires_review', 'failed', 'started')):
            found[identity['case_id']] = record['status']
    return found


def pending(case_ids, attempts):
    return [c for c in case_ids if c not in attempts]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, choices=MODELS)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--reasoning', choices=['server-default', 'off'], default='server-default')
    parser.add_argument('--run', action='store_true', help='Make local model calls; omit for a dry plan')
    args = parser.parse_args()
    config = json.loads(Path('data/pipeline-config.json').read_text())
    ids = dev_case_ids(json.loads(Path(config['dev_cases_path']).read_text()))
    reasoning = 'server default' if args.reasoning == 'server-default' else 'off'
    attempts = saved_attempts(args.model, reasoning=reasoning, timeout=args.timeout)
    todo = pending(ids, attempts)
    print(f'{len(ids)} development cases; {len(ids) - len(todo)} already attempted (reused, no repeat); '
          f'{len(todo)} to run with {args.model} (reasoning {reasoning}, timeout {args.timeout}s).')
    stuck = [c for c, s in attempts.items() if s == 'started']
    if stuck:
        print('Interrupted earlier attempts recorded as failures, not retried: ' + ', '.join(sorted(stuck)))
    if not args.run:
        print('Dry plan only: no model calls. Add --run to start.')
        return 0
    failures = 0
    for case_id in todo:
        result = subprocess.run([sys.executable, '-u', '-m', 'disputelens.generate_answer', '--dev-case', case_id,
                                 '--context-source', 'full', '--model', args.model, '--reasoning', args.reasoning, '--timeout', str(args.timeout), '--run'], check=False)
        failures = failures + 1 if result.returncode else 0
        print(f'[{case_id}] exit={result.returncode}; consecutive failures={failures}', flush=True)
        if failures >= MAX_CONSECUTIVE_FAILURES:
            print('STOP: three consecutive failures; no retries. Inspect saved attempts.')
            return 1
    print('Batch finished. Structural checks only; semantic review is separate.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
