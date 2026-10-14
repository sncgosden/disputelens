"""One explicit Claude diagnostic using a saved development context pack."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

from .build_index import digest
from .client import ModelError, configured_models
from .embed_batch import safe_error, write_json
from .grounded_answer import SYSTEM, build_answer_prompt, validate_answer
from .paid_budget import reserve_paid_request, token_cost


def final_text(data):
    if data.get('stop_reason') != 'end_turn':
        raise ModelError('Claude did not finish normally; do not score this response.')
    blocks = data.get('content')
    if not isinstance(blocks, list):
        raise ModelError('Unexpected Claude response.')
    text = ''.join(b['text'] for b in blocks if b.get('type') == 'text')
    if not text.strip():
        raise ModelError('Claude returned no final answer.')
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev-case', required=True)
    parser.add_argument('--context-source', choices=['focused', 'full'], default='focused',
                        help='Choose the saved context experiment; defaults to focused')
    parser.add_argument('--run', action='store_true', help='Send one paid Claude API request')
    parser.add_argument('--budget', type=Path, help='Reserve this request against a persistent counted budget')
    args = parser.parse_args(argv)
    models = configured_models()
    try:
        model = os.getenv('CLAUDE_MODEL')
        key = os.getenv('ANTHROPIC_API_KEY')
        if not model or not key:
            raise ModelError('Set CLAUDE_MODEL and ANTHROPIC_API_KEY in the ignored .env file.')
        config = json.loads(Path('data/pipeline-config.json').read_text())
        pointer_path = ('data/indexes/focused-context/latest.json' if args.context_source == 'focused'
                        else 'data/indexes/context-eval/latest.json')
        pointer = json.loads(Path(pointer_path).read_text())
        summary_path = Path(pointer['summary_path'])
        summary = json.loads(summary_path.read_text())
        if (summary['status'] != 'complete'
                or summary['identity']['dev_cases_sha256'] != digest(config['dev_cases_path'])
                or summary['identity']['builder_code_sha256'] != digest(Path(__file__).with_name('context_pack.py'))):
            raise ModelError('Selected context evaluation is incomplete or stale.')
        cases = json.loads(Path(config['dev_cases_path']).read_text())
        case = next((c for c in cases if c['case_id'] == args.dev_case and c['split'] == 'dev'), None)
        if case is None:
            raise ModelError('Unknown development case; holdout is not loaded.')
        pack_path = summary_path.parent / 'packs' / (case['case_id'] + '.json')
        pack = json.loads(pack_path.read_text())
        if (pack['evaluation_identity'] != summary['identity'] or pack['question'] != case['question']
                or pack['trusted_settings'] != case['filters']):
            raise ModelError('Pack question, scope or configuration mismatch.')
        prompt = build_answer_prompt(pack['question'], pack)
        identity = {'case_id': case['case_id'], 'model': model, 'provider': 'claude',
                    'context_source': args.context_source, 'context_pack_sha256': digest(pack_path),
                    'prompt_sha256': hashlib.sha256((SYSTEM + '\n' + prompt).encode()).hexdigest(),
                    'answer_code_sha256': digest(Path(__file__).with_name('grounded_answer.py')),
                    'runner_code_sha256': digest(__file__), 'max_tokens': 8192,
                    'temperature': 'provider default', 'thinking': 'not requested',
                    'timeout_seconds': 300}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        output = Path('data/indexes/answer-trials') / (case['case_id'] + '-claude-' + run_id + '.json')
        print(f'Model: {model}; {args.context_source} pack: {pack_path}', flush=True)
        if not args.run:
            print('Configuration and pack checked. No API request or token-capacity check performed.')
            print('Add --run to send one paid request. Source extracts will be sent to Anthropic.')
            return 0
        if output.exists():
            raise ModelError(f'Attempt already saved at {output}; inspect before another call.')
        if args.budget:
            reserve_paid_request(args.budget, run_id, identity['prompt_sha256'], model, 8192)
        record = {'status': 'started', 'identity': identity, 'question': pack['question'],
                  'trusted_settings': pack['trusted_settings'], 'context_pack_path': str(pack_path)}
        if args.budget:
            record['budget_path'] = str(args.budget)
        write_json(output, record)
        started = time.perf_counter()
        print('Sending one paid Claude request; no retries or fallback...', flush=True)
        try:
            data = models._request('POST', 'https://api.anthropic.com/v1/messages',
                headers={'x-api-key': key, 'anthropic-version': '2023-06-01'},
                timeout=httpx.Timeout(300, connect=5),
                json={'model': model, 'max_tokens': 8192, 'system': SYSTEM,
                      'messages': [{'role': 'user', 'content': prompt}]})
            record.update(raw_api_response=data, usage=data.get('usage', {}),
                          generation_seconds=time.perf_counter() - started)
            write_json(output, record)
            pricing = json.loads(Path('data/claude-pricing.json').read_text())
            usage = record['usage']
            if (model == pricing['model'] and data.get('service_tier', 'standard') == 'standard'
                    and usage.get('service_tier', 'standard') == 'standard'
                    and usage.get('inference_geo', 'global') == 'global'
                    and not usage.get('cache_creation_input_tokens', 0)
                    and not usage.get('cache_read_input_tokens', 0)):
                record['calculated_api_cost_usd'] = token_cost(usage.get('input_tokens'), usage.get('output_tokens'), pricing)
                record['pricing_source'] = pricing['source']
                write_json(output, record)
            text = final_text(data)
            record['raw_response'] = text
            checked = validate_answer(text, pack)
            record.update(status='complete_requires_review', **checked)
            write_json(output, record)
        except Exception as error:
            record.update(status='failed', error=safe_error(error),
                          generation_seconds=time.perf_counter() - started)
            write_json(output, record)
            raise ModelError(f'{safe_error(error)} Failure saved at {output}; no automatic retry.') from None
        print('ANSWER STATUS: ' + checked['answer']['status'])
        for claim in checked['answer']['claims']:
            print('- ' + claim['text'] + ' ' + ' '.join('[' + c['id'] + ']' for c in claim['citations']))
        print('Usage: ' + json.dumps(record['usage']))
        print(f'Seconds: {record["generation_seconds"]:.1f}; SAVED: {output}')
        print('Citation IDs and extracts checked; semantic support still requires review.')
        print('One development trial only. No holdout, index changes or GitHub sync.')
        return 0
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    finally:
        models.close()


if __name__ == '__main__':
    raise SystemExit(main())
