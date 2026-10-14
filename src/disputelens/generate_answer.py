"""Check or run one local grounded answer from a saved development context pack."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .build_index import digest
from .client import ModelError, configured_models
from .embed_batch import safe_error, write_json
from .grounded_answer import SYSTEM, build_answer_prompt, validate_answer
from .rerank_trial import check_budget, final_ranking_text


def request_answer(models, prompt, model_id, max_tokens, reasoning=None, timeout=300):
    address = urlparse(models.base)
    payload = {'model': model_id, 'input': prompt, 'system_prompt': SYSTEM,
               'max_output_tokens': max_tokens, 'temperature': 0.2, 'store': False}
    if reasoning is not None:
        payload['reasoning'] = reasoning
    return models._request('POST', f'{address.scheme}://{address.netloc}/api/v1/chat',
        headers=models._local_headers(), timeout=httpx.Timeout(timeout, connect=5), json=payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev-case', required=True)
    parser.add_argument('--model', default='qwen3.5-4b', choices=['qwen3.5-4b', 'qwen3.5-9b-mlx'])
    parser.add_argument('--run', action='store_true', help='Make one local answer-generation call')
    parser.add_argument('--context-source', choices=['full', 'focused'], default='full',
                        help='Choose the saved context experiment explicitly; defaults stay unchanged')
    parser.add_argument('--max-tokens', type=int, default=8192)
    parser.add_argument('--timeout', type=int, default=300, help='Seconds per call (300-1800); recorded in the attempt identity')
    parser.add_argument('--reasoning', choices=['server-default', 'off'], default='server-default',
                        help='off sends reasoning=off; a separate documented variant with its own saved identity')
    args = parser.parse_args()
    models = configured_models()
    try:
        if not 300 <= args.timeout <= 1800:
            raise ModelError('Use timeout between 300 and 1800 seconds.')
        if not 256 <= args.max_tokens <= 8192:
            raise ModelError('Use max-tokens between 256 and 8192.')
        if urlparse(models.base).hostname not in ('localhost', '127.0.0.1', '::1') or os.getenv('LM_API_TOKEN'):
            raise ModelError('This check needs unauthenticated local LM Studio.')
        config = json.loads(Path('data/pipeline-config.json').read_text())
        pointer_path = ('data/indexes/context-eval/latest.json' if args.context_source == 'full'
                        else 'data/indexes/focused-context/latest.json')
        pointer = json.loads(Path(pointer_path).read_text())
        summary_path = Path(pointer['summary_path'])
        summary = json.loads(summary_path.read_text())
        if (summary['status'] != 'complete'
                or summary['identity']['dev_cases_sha256'] != digest(config['dev_cases_path'])
                or summary['identity']['builder_code_sha256'] != digest(Path(__file__).with_name('context_pack.py'))):
            raise ModelError('Context evaluation is incomplete or stale; verify packs before generation.')
        cases = json.loads(Path(config['dev_cases_path']).read_text())
        case = next((c for c in cases if c['case_id'] == args.dev_case and c['split'] == 'dev'), None)
        if case is None:
            raise ModelError('Unknown development case; holdout is not loaded.')
        pack_path = summary_path.parent / 'packs' / (case['case_id'] + '.json')
        pack = json.loads(pack_path.read_text())
        if (pack['evaluation_identity'] != summary['identity'] or pack['question'] != case['question']
                or pack['trusted_settings'] != case['filters']):
            raise ModelError('Pack question, scope or configuration mismatch.')
        # Only the question and evidence pack enter generation, never gold claims.
        prompt = build_answer_prompt(pack['question'], pack)
        import lmstudio as lms
        model = next((m for m in lms.list_loaded_models('llm') if m.identifier == args.model), None)
        if model is None:
            raise ModelError(f'Load {args.model} in LM Studio first.')
        chat = lms.Chat(SYSTEM)
        chat.add_user_message(prompt)
        budget = check_budget(len(model.tokenize(model.apply_prompt_template(chat))),
                              model.get_context_length(), args.max_tokens)
        print(f'PASS: {budget["prompt_tokens"]} prompt tokens + {args.max_tokens} output + 64 reserve '
              f'fit {budget["loaded_context_tokens"]} loaded context tokens.', flush=True)
        identity = {'case_id': case['case_id'], 'model': args.model,
                    'context_source': args.context_source,
                    'context_pack_sha256': digest(pack_path),
                    'prompt_sha256': hashlib.sha256((SYSTEM + '\n' + prompt).encode()).hexdigest(),
                    'answer_code_sha256': digest(Path(__file__).with_name('grounded_answer.py')),
                    'runner_code_sha256': digest(__file__), 'max_tokens': args.max_tokens,
                    'temperature': 0.2, 'reasoning': 'server default' if args.reasoning == 'server-default' else 'off',
                    'endpoint': '/api/v1/chat', 'timeout_seconds': args.timeout, 'budget': budget}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        output = Path('data/indexes/answer-trials') / (case['case_id'] + '-' + run_id + '.json')
        if not args.run:
            check_path = output.with_name(output.stem + '-check.json')
            write_json(check_path, {'status': 'context_checked', 'identity': identity})
            print(f'SAVED: {check_path}\nNo answer generated; no Claude calls, holdout or GitHub sync.')
            return 0
        if output.exists():
            raise ModelError(f'Attempt already saved at {output}; inspect before another call.')
        record = {'status': 'started', 'identity': identity, 'question': pack['question'],
                  'trusted_settings': pack['trusted_settings'], 'context_pack_path': str(pack_path)}
        write_json(output, record)
        started = time.perf_counter()
        print(f'Generating one grounded answer locally with {args.model}; waiting for final JSON...', flush=True)
        try:
            data = request_answer(models, prompt, args.model, args.max_tokens, None if args.reasoning == 'server-default' else 'off', args.timeout)
            record.update(raw_api_response=data, usage=data.get('stats', {}),
                          generation_seconds=time.perf_counter() - started)
            write_json(output, record)
            text = final_ranking_text(data, args.max_tokens, allow_reasoning=args.reasoning == 'server-default')
            record['raw_response'] = text
            checked = validate_answer(text, pack)
            record.update(status='complete_requires_review', **checked)
            write_json(output, record)
        except Exception as error:
            record.update(status='failed', error=safe_error(error),
                          generation_seconds=time.perf_counter() - started)
            write_json(output, record)
            raise ModelError(f'{safe_error(error)} Failure saved at {output}; no automatic retry.') from None
        answer = checked['answer']
        print('ANSWER STATUS: ' + answer['status'])
        for claim in answer['claims']:
            print('- ' + claim['text'] + ' ' + ' '.join('[' + c['id'] + ']' for c in claim['citations']))
        for missing in answer['missing_information']:
            print('MISSING: ' + missing)
        print(f'Citation IDs and supporting extracts checked. Semantic support still needs review. '
              f'Seconds: {record["generation_seconds"]:.1f}\nSAVED: {output}')
        print('One development answer only. No merchant action, Claude calls, holdout or GitHub sync.')
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    finally:
        models.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
