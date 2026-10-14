"""Count frozen Claude inputs using the free endpoint; never generate an answer."""
import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

from .build_index import digest
from .client import ModelError, configured_models
from .embed_batch import safe_error, write_json
from .grounded_answer import SYSTEM, build_answer_prompt
from .paid_budget import token_cost


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count-inputs', action='store_true', help='Send prompts to the free token-count endpoint')
    args = parser.parse_args()
    models = configured_models()
    try:
        pp = Path(json.loads(Path('data/indexes/answer-eval-plan/latest.json').read_text())['plan_path'])
        plan = json.loads(pp.read_text())
        pricing = json.loads(Path('data/claude-pricing.json').read_text())
        model = pricing['model']
        if plan['identity']['answer_code_sha256'] != digest(Path(__file__).with_name('grounded_answer.py')):
            raise ModelError('Answer prompt/validator changed since plan; prepare a fresh plan.')
        jobs = [j for j in plan['jobs'] if j['provider'] == 'claude']
        if len(jobs) != 45 or any(j['model'] != model for j in jobs):
            raise ModelError('Expected 45 frozen Sonnet 5.5 jobs.')
        identity = {'plan_sha256': digest(pp), 'pricing_sha256': digest('data/claude-pricing.json'),
                    'max_calls': 45, 'max_usd': 6.0, 'max_output_tokens': 8192,
                    'input_margin': '10% plus 512 tokens per request'}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        directory = Path('data/indexes/paid-budgets') / key
        budget_path = directory / 'budget.json'
        if budget_path.exists():
            print(f'Existing budget preserved: {budget_path}; no reset or new calls.')
            return 0
        print('LIMITS: 45 paid calls; 8192 output tokens per call; $6 reservation allowance.')
        if not args.count_inputs:
            print('No API calls. Add --count-inputs to send the 45 frozen prompts to the free counting endpoint.')
            return 0
        if os.getenv('CLAUDE_MODEL') != model or not os.getenv('ANTHROPIC_API_KEY'):
            raise ModelError('Configured Claude model/key does not match the priced plan.')
        counted = []
        for n, job in enumerate(jobs, 1):
            path = Path(job['context_pack_path'])
            if digest(path) != job['context_pack_sha256']:
                raise ModelError('Frozen context fingerprint changed.')
            pack = json.loads(path.read_text())
            prompt = build_answer_prompt(pack['question'], pack)
            actual_sha = hashlib.sha256((SYSTEM + '\n' + prompt).encode()).hexdigest()
            if actual_sha != job['prompt_sha256']:
                raise ModelError('Frozen prompt fingerprint changed.')
            cache = directory / 'counts' / (job['case_id'] + '.json')
            if cache.exists():
                data = json.loads(cache.read_text())
                if data['prompt_sha256'] != actual_sha or data['model'] != model:
                    raise ModelError('Token-count cache identity mismatch.')
                inputs = data['input_tokens']
            else:
                data = models._request('POST', 'https://api.anthropic.com/v1/messages/count_tokens',
                    headers={'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'},
                    json={'model': model, 'system': SYSTEM,
                          'messages': [{'role': 'user', 'content': prompt}]})
                inputs = data.get('input_tokens')
                token_cost(inputs, 0, pricing)
                write_json(cache, {'prompt_sha256': actual_sha, 'model': model, 'input_tokens': inputs})
            input_allowance = math.ceil(inputs * 1.1) + 512
            counted.append({**job, 'counted_input_tokens': inputs, 'input_token_allowance': input_allowance,
                            'reserved_usd': token_cost(input_allowance, 8192, pricing)})
            print(f'COUNTED {n}/45 {job["case_id"]}: {inputs} input tokens', flush=True)
        total = sum(j['reserved_usd'] for j in counted)
        budget = {'status': 'prepared', 'identity': identity, 'model': model, 'pricing': pricing,
                  'max_calls': 45, 'max_usd': 6.0, 'max_output_tokens': 8192,
                  'jobs': counted, 'reservations': {},
                  'full_run_reserved_usd': total,
                  'full_run_fits_allowance': total <= 6,
                  'limitations': 'Reservation guard is not an account billing cap. Counts are estimates; taxes excluded. Failed/unknown usage retains reservations. All 45 calls budgeted before reuse.'}
        write_json(budget_path, budget)
        write_json(Path('data/indexes/paid-budgets/latest.json'), {'budget_path': str(budget_path)})
        print('INPUT TOKENS COUNTED: ' + str(sum(j['counted_input_tokens'] for j in counted)))
        print(f'BUFFERED INPUT + MAX OUTPUT ALLOWANCE: ${total:.4f}')
        print('FULL RUN FITS $6: ' + str(total <= 6))
        print(f'SAVED BUDGET: {budget_path}')
        print('No answer generation, paid Messages calls, holdout or GitHub sync.')
        return 0
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    finally:
        models.close()


if __name__ == '__main__':
    raise SystemExit(main())
