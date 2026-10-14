"""Separate six-case scope experiment: dry check, token count, explicit budgeted run."""
import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .build_index import digest
from .client import ModelError, configured_models
from .claude_answer_trial import final_text
from .embed_batch import safe_error, write_json
from .grounded_answer import SYSTEM, build_answer_prompt, validate_answer
from .paid_budget import reserve_paid_request, token_cost

PROTOCOL = Path('eval/experiments/scope-guard-v1/protocol.json')


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def prepare_jobs(protocol, candidate):
    contract = protocol['generation_contract']
    if (sha(SYSTEM) != protocol['baseline_system_sha256']
            or sha(candidate) != protocol['candidate_system_sha256']
            or contract['temperature'] != 'provider default'
            or contract['max_output_tokens'] != 8192):
        raise ModelError('Frozen prompt or generation contract mismatch.')
    expected = ['E13', 'E22', 'E23', 'E10', 'E30', 'E46']
    if [c['case_id'] for c in protocol['cases']] != expected:
        raise ModelError('Expected the six preregistered development cases.')
    jobs = []
    for case in protocol['cases']:
        if (digest(case['pack_path']) != case['pack_sha256']
                or digest(case['baseline_attempt_path']) != case['baseline_attempt_sha256']):
            raise ModelError('Frozen input or baseline attempt changed.')
        pack = json.loads(Path(case['pack_path']).read_text())
        if pack['question'] != case['question'] or pack['trusted_settings'] != case['filters']:
            raise ModelError('Question/scope mismatch.')
        prompt = build_answer_prompt(case['question'], pack)
        jobs.append({'case_id': case['case_id'], 'prompt': prompt,
                     'prompt_sha256': sha(candidate + '\n' + prompt), 'pack': pack})
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--count-inputs', action='store_true', help='Send six prompts to token-count endpoint; no generation')
    group.add_argument('--run', action='store_true', help='Generate up to six budgeted paid answers, never retry a reservation')
    parser.add_argument('--limit', type=int, default=6)
    args = parser.parse_args()
    models = None
    try:
        if not 1 <= args.limit <= 6:
            raise ModelError('Limit must be 1–6.')
        protocol = json.loads(PROTOCOL.read_text())
        candidate = Path(protocol['candidate_path']).read_text()
        jobs = prepare_jobs(protocol, candidate)
        pricing = json.loads(Path('data/claude-pricing.json').read_text())
        model = protocol['generation_contract']['planned_model']
        if pricing['model'] != model:
            raise ModelError('Priced model differs from protocol.')
        identity = {'protocol_sha256': digest(PROTOCOL), 'runner_sha256': digest(__file__),
                    'validator_sha256': digest(Path(__file__).with_name('grounded_answer.py')),
                    'pricing_sha256': digest('data/claude-pricing.json')}
        directory = Path('data/indexes/scope-guard-trials') / sha(json.dumps(identity, sort_keys=True))[:24]
        budget_path = directory / 'budget.json'
        print('CHECKED: 3 scope targets + 3 regression controls; only system prompt changes.')
        print('OUTPUT: ' + str(directory))
        print('LIMITS: 6 calls, $1 conservative reservation allowance, 8192 output tokens per call.')
        if not args.run and not args.count_inputs:
            print('Offline check only. No API requests. Use --count-inputs before paid execution.')
            return 0
        load_dotenv('.env')
        if os.getenv('CLAUDE_MODEL') != model or not os.getenv('ANTHROPIC_API_KEY'):
            raise ModelError('Configured model/key does not match protocol.')
        models = configured_models()
        headers = {'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'}
        def payload(job):
            return {'model': model, 'system': candidate,
                    'messages': [{'role': 'user', 'content': job['prompt']}]}
        if args.count_inputs:
            if budget_path.exists():
                print('Existing budget preserved; no counting calls or reset.')
                return 0
            counted = []
            for job in jobs:
                cache = directory / 'counts' / (job['case_id'] + '.json')
                if cache.exists():
                    data = json.loads(cache.read_text())
                    if data['prompt_sha256'] != job['prompt_sha256']:
                        raise ModelError('Count cache mismatch.')
                    inputs = data['input_tokens']
                else:
                    data = models._request('POST', 'https://api.anthropic.com/v1/messages/count_tokens',
                                           headers=headers, json=payload(job))
                    inputs = data.get('input_tokens')
                    token_cost(inputs, 0, pricing)
                    write_json(cache, {'prompt_sha256': job['prompt_sha256'], 'input_tokens': inputs})
                allowance = math.ceil(inputs * 1.1) + 512
                counted.append({'case_id': job['case_id'], 'prompt_sha256': job['prompt_sha256'],
                                'counted_input_tokens': inputs, 'reserved_usd': token_cost(allowance, 8192, pricing)})
                print('COUNTED: ' + job['case_id'] + ' ' + str(inputs), flush=True)
            total = sum(j['reserved_usd'] for j in counted)
            write_json(budget_path, {'identity': identity, 'model': model, 'pricing': pricing,
                                    'max_calls': 6, 'max_usd': 1.0, 'max_output_tokens': 8192,
                                    'jobs': counted, 'reservations': {}, 'full_run_reserved_usd': total,
                                    'full_run_fits_allowance': total <= 1.0})
            print(f'BUFFERED INPUT + MAX OUTPUT: ${total:.4f}; fits $1: {total <= 1.0}')
            print('No answer-generation calls. Budget is a reservation guard, not an account billing cap; taxes excluded.')
            return 0
        budget = json.loads(budget_path.read_text())
        if budget['identity'] != identity or not budget['full_run_fits_allowance']:
            raise ModelError('Budget stale or six-call allowance exceeds $1.')
        write_json(directory / 'protocol-snapshot.json', protocol)
        sent = 0
        for job in jobs:
            attempt_id = job['case_id'] + '-' + job['prompt_sha256'][:24]
            target = directory / 'attempts' / (job['case_id'] + '.json')
            current = json.loads(budget_path.read_text())
            if target.exists() or attempt_id in current['reservations']:
                print('PRESERVED: ' + job['case_id'] + ' existing attempt/reservation; no retry.')
                continue
            if sent >= args.limit:
                break
            reserve_paid_request(budget_path, attempt_id, job['prompt_sha256'], model, 8192)
            record = {'status': 'started', 'identity': identity, 'case_id': job['case_id'],
                      'prompt_sha256': job['prompt_sha256'], 'semantic_review': 'pending'}
            write_json(target, record)
            started = time.perf_counter()
            try:
                print('SENDING: ' + job['case_id'] + '; no retry...', flush=True)
                data = models._request('POST', 'https://api.anthropic.com/v1/messages', headers=headers,
                                       timeout=httpx.Timeout(300, connect=5), json={**payload(job), 'max_tokens': 8192})
                record.update(raw_api_response=data, usage=data.get('usage', {}), generation_seconds=time.perf_counter()-started)
                write_json(target, record)
                text = final_text(data)
                record['raw_response'] = text
                write_json(target, record)
                record.update(validate_answer(text, job['pack']), status='complete_requires_review')
                usage = record['usage']
                if (data.get('service_tier', 'standard') == 'standard' and usage.get('service_tier','standard') == 'standard'
                        and usage.get('inference_geo','global') == 'global'
                        and not usage.get('cache_creation_input_tokens',0) and not usage.get('cache_read_input_tokens',0)):
                    record['calculated_api_cost_usd'] = token_cost(usage.get('input_tokens'), usage.get('output_tokens'), pricing)
                write_json(target, record)
                sent += 1
                print('SAVED: ' + str(target), flush=True)
            except Exception as error:
                record.update(status='failed', error=safe_error(error), generation_seconds=time.perf_counter()-started)
                write_json(target, record)
                raise ModelError('Failure retained; batch stopped without retry: ' + safe_error(error)) from None
        print('New calls: ' + str(sent) + '. Semantic promotion gates remain pending; baseline and holdout unchanged.')
        return 0
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    finally:
        if models is not None:
            models.close()


if __name__ == '__main__':
    raise SystemExit(main())
