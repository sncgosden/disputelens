"""Authorised paid runner for flagged-answer-v1: 2 free token counts, then 2 Claude calls, no retries.

Stages:  count  (free count_tokens, writes budget)   run  (two generation calls).
Approved by the user on 2026-10-08: model claude-sonnet-5-5, cap 0.30 USD, no retries, stop on first failure.
"""
import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path

import httpx

from .claude_answer_trial import final_text
from .client import ModelError, configured_models
from .embed_batch import safe_error, write_json
from .flagged_answer_trial import CASES, MODEL, PROTOCOL, OUT, score
from .grounded_answer import validate_answer
from .paid_budget import reserve_paid_request, token_cost
from .scope_detector import BUNDLE

PRICING = Path('data/claude-pricing.json')
MAX_USD = 0.30


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('count', 'run'), required=True)
    parser.add_argument('--only', choices=CASES, help='continuation: run just this case (labelled in the record)')
    args = parser.parse_args()
    stage, only = args.stage, args.only
    root = OUT / sha(PROTOCOL)[:24]
    prepared = json.loads((root / 'prepared.json').read_text())
    pricing = json.loads(PRICING.read_text())
    budget_path = root / 'budget.json'
    models = configured_models()
    try:
        if pricing['model'] != MODEL or os.getenv('CLAUDE_MODEL') != MODEL or not os.getenv('ANTHROPIC_API_KEY'):
            raise ModelError('Configured model/key does not match the authorised model.')
        headers = {'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'}
        cases = {c['case_id']: c for c in json.loads(BUNDLE.read_text())['cases']}
        jobs = []
        for cid in CASES:
            body = json.loads((root / f'{cid}-request.json').read_text())
            fingerprint = hashlib.sha256((body['system'] + '\n' + body['messages'][0]['content']).encode()).hexdigest()
            if fingerprint != prepared['cases'][cid]['prompt_sha256'] or body['model'] != MODEL or body['max_tokens'] != 8192:
                raise ModelError(f'{cid}: request changed since preparation.')
            jobs.append((cid, body, fingerprint))
        if stage == 'count':
            if budget_path.exists():
                raise ModelError('Budget already exists; do not recount automatically.')
            counted = []
            for cid, body, fingerprint in jobs:
                print(f'COUNTING {cid} input tokens; no generation.', flush=True)
                data = models._request('POST', 'https://api.anthropic.com/v1/messages/count_tokens', headers=headers,
                                       json={k: v for k, v in body.items() if k != 'max_tokens'})
                inputs = data.get('input_tokens')
                token_cost(inputs, 0, pricing)
                allowance = math.ceil(inputs * 1.1) + 512
                counted.append({'case_id': cid, 'prompt_sha256': fingerprint, 'counted_input_tokens': inputs,
                                'input_token_allowance': allowance, 'reserved_usd': token_cost(allowance, 8192, pricing)})
            total = sum(j['reserved_usd'] for j in counted)
            write_json(budget_path, {'status': 'prepared', 'identity': {'protocol_sha256': sha(PROTOCOL), 'pricing_sha256': sha(PRICING)},
                                     'model': MODEL, 'pricing': pricing, 'max_calls': 2, 'max_usd': MAX_USD,
                                     'max_output_tokens': 8192, 'jobs': counted, 'reservations': {},
                                     'full_run_reserved_usd': total, 'full_run_fits_allowance': total <= MAX_USD})
            print(f'RESERVED MAXIMUM: ${total:.4f}; two calls, no retries.', flush=True)
            if total > MAX_USD:
                raise ModelError('Buffered allowance exceeds the $0.30 cap; no paid calls.')
        else:
            budget = json.loads(budget_path.read_text())
            if budget['identity']['protocol_sha256'] != sha(PROTOCOL) or not budget['full_run_fits_allowance']:
                raise ModelError('Prepared budget does not match the protocol.')
            for cid, body, fingerprint in jobs:
                if only and cid != only:
                    continue
                out = root / f'{cid}-claude-attempt.json'
                if out.exists():
                    raise ModelError('Attempt already saved; no retry.')
                attempt_id = hashlib.sha256((cid + fingerprint + MODEL).encode()).hexdigest()[:24]
                reserve_paid_request(budget_path, attempt_id, fingerprint, MODEL, 8192)
                pack = cases[cid]['frozen_context_pack']
                record = {'status': 'started', 'case_id': cid, 'model': MODEL, 'prompt_sha256': fingerprint,
                          'protocol_sha256': sha(PROTOCOL), 'max_tokens': 8192, 'diagnostic_only': True,
                          'runner_sha256': sha(__file__),
                          'continuation': 'user-authorised E22-only run after E13 failed M1; declared stop rule relaxed by explicit user instruction' if only else None}
                write_json(out, record)
                started = time.perf_counter()
                print(f'GENERATING {cid}: one authorised call; no retry.', flush=True)
                try:
                    data = models._request('POST', 'https://api.anthropic.com/v1/messages', headers=headers,
                                           timeout=httpx.Timeout(300, connect=5), json=body)
                    usage = data.get('usage', {})
                    record.update(raw_api_response=data, usage=usage, generation_seconds=time.perf_counter() - started)
                    if usage.get('input_tokens') is not None and usage.get('output_tokens') is not None:
                        record['calculated_api_cost_usd'] = token_cost(usage['input_tokens'], usage['output_tokens'], pricing)
                    text = final_text(data)
                    record['raw_response'] = text
                    checked = validate_answer(text, pack)
                    record.update(status='complete_requires_review', **checked)
                    record['mechanical'] = score(cases[cid], checked['answer'])
                    write_json(out, record)
                    print(f"{cid} {checked['answer']['status']}; {record['generation_seconds']:.1f}s; {out}", flush=True)
                except Exception as error:
                    record.update(status='failed', error=safe_error(error), generation_seconds=time.perf_counter() - started)
                    write_json(out, record)
                    raise ModelError('Failure saved; stopping without retries: ' + safe_error(error)) from None
    finally:
        models.close()


if __name__ == '__main__':
    main()
