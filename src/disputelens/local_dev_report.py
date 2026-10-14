"""Offline summary of saved local development attempts. No model calls, development cases only."""
import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

TRIALS = Path('data/indexes/answer-trials')
OUT = Path('data/indexes/local-dev-report')


def load(model, directory=TRIALS, reasoning='server default', timeout=300):
    rows = {}
    for path in Path(directory).glob('*.json'):
        try:
            r = json.loads(path.read_text())
        except ValueError:
            continue
        i = r.get('identity') or {}
        if i.get('model') == model and i.get('context_source') == 'full' and i.get('max_tokens') == 8192 and i.get('reasoning', 'server default') == reasoning and i.get('timeout_seconds', 300) == timeout \
                and r.get('status') in ('complete_requires_review', 'failed', 'started'):
            rows[i['case_id']] = r
    return rows


CLAUDE_SUMMARY = Path('data/indexes/answer-eval-plan/c36f49c3b45e0291a3d40299/claude-development-summary.json')


def claude_failures(path=CLAUDE_SUMMARY):
    """Final Claude failures from the saved 45-case development summary, not earlier pilot attempts."""
    cases = json.loads(Path(path).read_text())['cases']
    return {c['case_id'] for c in cases if c['status'] != 'citation_valid_requires_review'}


def summarise(rows, claude_failed=frozenset()):
    ok = {c: r for c, r in rows.items() if r['status'] == 'complete_requires_review'}
    bad = {c: r for c, r in rows.items() if r['status'] != 'complete_requires_review'}
    times = sorted(r.get('generation_seconds', 0) for r in rows.values() if r.get('generation_seconds'))
    errors = Counter((r.get('error') or 'interrupted before result')[:90] for r in bad.values())
    statuses = Counter(r['answer']['status'] for r in ok.values() if 'answer' in r)
    return {
        'attempted': len(rows), 'citation_valid': len(ok), 'failed_or_interrupted': len(bad),
        'answer_status_counts': dict(statuses), 'failure_reasons': dict(errors),
        'failed_cases': sorted(bad), 'also_failed_for_claude': sorted(set(bad) & set(claude_failed)),
        'seconds': {'median': round(statistics.median(times), 1), 'p90': round(times[int(0.9 * (len(times) - 1))], 1),
                    'max': round(times[-1], 1), 'total_minutes': round(sum(times) / 60, 1)} if times else None,
        'limits': ['Structural validation only (JSON shape, citation IDs, exact quotes); semantic support not reviewed',
                   'Development cases only; holdout untouched', 'One sample per case; no aggregate accuracy claim'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='qwen3.5-4b')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--reasoning', choices=['server-default', 'off'], default='server-default')
    args = parser.parse_args()
    mode = 'server default' if args.reasoning == 'server-default' else 'off'
    summary = summarise(load(args.model, reasoning=mode, timeout=args.timeout), claude_failures())
    summary['reasoning'] = mode
    summary['timeout_seconds'] = args.timeout
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (args.model + ('' if mode == 'server default' else '-reasoning-off') + ('' if args.timeout == 300 else f'-timeout{args.timeout}') + '-summary.json')).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
