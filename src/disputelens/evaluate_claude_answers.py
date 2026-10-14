"""Budgeted, resumable development generation; no automatic retries or scoring claims."""
import argparse
import json
import os
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import claude_answer_trial
from .build_index import digest
from .client import ModelError
from .embed_batch import safe_error, write_json
from .grounded_answer import validate_answer
from .paid_budget import token_cost


def find_attempt(job):
    matches = []
    for path in Path('data/indexes/answer-trials').glob(job['case_id'] + '-claude-*.json'):
        r = json.loads(path.read_text())
        identity = r.get('identity', {})
        if all(identity.get(k) == job[k] for k in
               ('case_id', 'model', 'prompt_sha256', 'context_pack_sha256', 'max_tokens')):
            matches.append((path, r))
    # An input-matching failure is retained, never silently retried.
    return max(matches, key=lambda x: x[0].stat().st_mtime_ns) if matches else None


def review_record(job, saved, pricing):
    row = {'case_id': job['case_id'], 'status': 'not_run', 'semantic_review': 'pending'}
    if saved is None:
        return row
    path, record = saved
    row.update(attempt_path=str(path), attempt_sha256=digest(path),
               generation_seconds=record.get('generation_seconds'), usage=record.get('usage', {}))
    raw = record.get('raw_response')
    if record['status'] == 'complete_requires_review' and raw:
        try:
            checked = validate_answer(raw, json.loads(Path(job['context_pack_path']).read_text()))
            row.update(status='citation_valid_requires_review', answer_status=checked['answer']['status'],
                       answer=checked['answer'])
        except ModelError as error:
            row.update(status='generation_or_validation_failed', error=safe_error(error))
    else:
        row.update(status='generation_or_validation_failed', error=record.get('error',
                   'Attempt has no validated final answer; inspect before any manual recovery.'))
    usage = row['usage']
    if (isinstance(usage.get('input_tokens'), int) and isinstance(usage.get('output_tokens'), int)
            and usage.get('service_tier', 'standard') == 'standard'
            and usage.get('inference_geo', 'global') == 'global'
            and not usage.get('cache_creation_input_tokens', 0)
            and not usage.get('cache_read_input_tokens', 0)):
        row['calculated_api_cost_usd'] = token_cost(usage['input_tokens'], usage['output_tokens'], pricing)
    return row


def summarize(rows):
    durations = [r['generation_seconds'] for r in rows if isinstance(r.get('generation_seconds'), (int, float))]
    return {'expected_cases': len(rows),
            'citation_valid': sum(r['status'] == 'citation_valid_requires_review' for r in rows),
            'failed': sum(r['status'] == 'generation_or_validation_failed' for r in rows),
            'not_run': sum(r['status'] == 'not_run' for r in rows),
            'median_attempt_seconds': statistics.median(durations) if durations else None,
            'calculated_cost_usd_for_known_usage': sum(r.get('calculated_api_cost_usd', 0) for r in rows),
            'attempts_without_priced_usage': sum(r['status'] != 'not_run' and 'calculated_api_cost_usd' not in r for r in rows),
            'semantic_accuracy': 'not scored'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Execute explicit budgeted paid requests')
    parser.add_argument('--limit', type=int, default=5, help='Maximum new paid requests this invocation (1–45)')
    args = parser.parse_args()
    try:
        if not 1 <= args.limit <= 45:
            raise ModelError('Choose a limit from 1 to 45.')
        load_dotenv('.env')
        pp = Path(json.loads(Path('data/indexes/answer-eval-plan/latest.json').read_text())['plan_path'])
        bp = Path(json.loads(Path('data/indexes/paid-budgets/latest.json').read_text())['budget_path'])
        plan, budget = json.loads(pp.read_text()), json.loads(bp.read_text())
        if (budget['identity']['plan_sha256'] != digest(pp)
                or plan['identity']['answer_code_sha256'] != digest(Path(__file__).with_name('grounded_answer.py'))
                or budget['identity']['pricing_sha256'] != digest('data/claude-pricing.json')):
            raise ModelError('Budget, prompt or pricing differs from frozen plan.')
        jobs = [j for j in plan['jobs'] if j['provider'] == 'claude']
        if (len(jobs) != 45 or len({j['case_id'] for j in jobs}) != 45
                or any(j['model'] != budget['model'] for j in jobs)):
            raise ModelError('Expected 45 distinct counted Claude jobs.')
        if os.getenv('CLAUDE_MODEL') != budget['model']:
            raise ModelError('Configured Claude model differs from plan.')
        for j in jobs:
            if digest(j['context_pack_path']) != j['context_pack_sha256']:
                raise ModelError('Frozen context changed.')
        rows = [review_record(j, find_attempt(j), budget['pricing']) for j in jobs]
        before = summarize(rows)
        print(f'BEFORE: {before["citation_valid"]} citation-valid; {before["failed"]} failed; {before["not_run"]} not run.', flush=True)
        print(f'NEW REQUEST LIMIT: {args.limit}; persistent budget: {bp}', flush=True)
        if not args.run:
            print('Dry run only. Add --run for explicit paid execution. Saved matching failures will not be retried.')
            return 0
        if not os.getenv('ANTHROPIC_API_KEY'):
            raise ModelError('Set ANTHROPIC_API_KEY in ignored .env.')
        sent = 0
        for j, row in zip(jobs, rows):
            if row['status'] != 'not_run' or sent >= args.limit:
                continue
            result = claude_answer_trial.main(['--dev-case', j['case_id'], '--context-source', 'full',
                                               '--budget', str(bp), '--run'])
            saved = find_attempt(j)
            if saved is None:
                print('STOPPING BATCH: request did not create an attempt; check budget/configuration.', flush=True)
                break
            sent += 1
            row.update(review_record(j, saved, budget['pricing']))
            print(f'RECORDED: {j["case_id"]}; {row["status"]}; exit {result}', flush=True)
        output = pp.parent / 'claude-development-summary.json'
        summary = summarize(rows)
        write_json(output, {'identity': {'plan_sha256': digest(pp), 'budget_path': str(bp),
            'validator_sha256': digest(Path(__file__).with_name('grounded_answer.py')),
            'runner_sha256': digest(__file__)}, 'summary': summary, 'cases': rows,
            'new_attempts_this_run': sent,
            'limitations': ['Matching historical attempts included; their cost predates this budget.',
                           'Citation validity is not correctness, completeness or groundedness.',
                           'Failures and unrun cases stay in the 45-case denominator.',
                           'Known-usage cost excludes missing usage and taxes; not invoice reconciliation.']})
        print(f'TOTAL: {summary["citation_valid"]}/45 citation-valid; {summary["failed"]} failed; {summary["not_run"]} not run.')
        print(f'NEW ATTEMPTS: {sent}; MEDIAN ATTEMPT SECONDS: {summary["median_attempt_seconds"]}')
        print(f'KNOWN-USAGE COST USD: {summary["calculated_cost_usd_for_known_usage"]:.4f}; '
              f'unpriced attempts: {summary["attempts_without_priced_usage"]}')
        print(f'SAVED SUMMARY: {output}')
        print('Semantic review pending. No local model requests, holdout, index changes or GitHub sync.')
        return 0
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
