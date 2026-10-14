"""Check, then optionally rerank one saved hybrid development result locally."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .client import ModelError, configured_models
from .embed_batch import safe_error, write_json
from .rerank import SYSTEM, apply_order, build_prompt
from .retrieval_metrics import score_retrieval


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_budget(prompt_tokens, context_length, output_tokens, reserve=64):
    values = (prompt_tokens, context_length, output_tokens, reserve)
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
        raise ModelError('Invalid context-budget values.')
    required = prompt_tokens + output_tokens + reserve
    if context_length <= 0 or output_tokens <= 0 or required > context_length:
        raise ModelError(f'Full prompt needs {required} tokens including output and framing; '
                         f'loaded context is {context_length}. Reload with a larger context. '
                         'No text truncated and no generation request sent.')
    return {'prompt_tokens': prompt_tokens, 'output_allowance': output_tokens,
            'framing_reserve': reserve, 'required_tokens': required,
            'loaded_context_tokens': context_length, 'fits': True}


def request_ranking(models, prompt, model_id, max_tokens, reasoning=None):
    """Use native generation without requiring a model-specific reasoning switch."""
    address = urlparse(models.base)
    endpoint = f'{address.scheme}://{address.netloc}/api/v1/chat'
    payload = {
        'model': model_id, 'input': prompt, 'system_prompt': SYSTEM,
        'max_output_tokens': max_tokens,
        'temperature': 0.2, 'store': False,
    }
    if reasoning is not None:
        payload['reasoning'] = reasoning
    return models._request('POST', endpoint, headers=models._local_headers(), json=payload,
                           timeout=httpx.Timeout(300, connect=5))


def final_ranking_text(data, max_tokens, allow_reasoning=False):
    """Do not score an empty, truncated or unexpectedly reasoning-enabled response."""
    try:
        stats = data['stats']
        count = stats['total_output_tokens']
        reasoning = stats['reasoning_output_tokens']
        if (isinstance(count, bool) or not isinstance(count, (int, float))
                or not 0 <= count < max_tokens):
            raise ModelError('Response reached the output allowance or has invalid token stats.')
        if not allow_reasoning and (reasoning != 0 or any(item['type'] == 'reasoning' for item in data['output'])):
            raise ModelError('Server returned reasoning despite reasoning=off. Inspect the saved response.')
        permitted = {'message', 'reasoning'} if allow_reasoning else {'message'}
        if any(item['type'] not in permitted for item in data['output']):
            raise ModelError('Unexpected native output type; response not scored.')
        text = ''.join(item['content'] for item in data['output'] if item['type'] == 'message')
        if not isinstance(text, str) or not text.strip():
            raise ModelError('No final answer returned; only reasoning or empty output received. Inspect the saved response.')
        return text
    except (KeyError, TypeError):
        raise ModelError('Unexpected native API response. Inspect the saved response.') from None


def load_saved_case(case_id, config):
    case_path = Path(config['dev_cases_path'])
    cases = json.loads(case_path.read_text())
    case = next((c for c in cases if c['case_id'] == case_id and c['split'] == 'dev'), None)
    if case is None:
        raise ModelError('Unknown development case. Holdout is not loaded.')
    pointer = json.loads(Path('data/indexes/retrieval-eval/hybrid-latest.json').read_text())
    saved_path = Path(pointer['run_directory']) / 'cases' / f'{case_id}.json'
    saved = json.loads(saved_path.read_text())
    identity = saved['identity']
    unit_path = Path(config['embedding_units_path'])
    if (identity['strategy'] != 'hybrid'
            or identity['dev_cases_sha256'] != sha(case_path)
            or identity['embedding_units_sha256'] != sha(unit_path)
            or identity['index_manifest_sha256'] != sha('data/indexes/index-manifest.json')
            or identity['metric_contract_sha256'] != sha('eval/retrieval-metric-contract.json')
            or saved['case_id'] != case_id or saved['question'] != case['question']
            or saved['filters'] != case['filters']):
        raise ModelError('Saved candidates do not match current development data/configuration.')
    units = json.loads(unit_path.read_text())['chunks']
    by_id = {u['chunk_id']: u for u in units}
    if len(saved['results']) != 20:
        raise ModelError('This trial requires the saved twenty hybrid candidates.')
    for result in saved['results']:
        if by_id.get(result['unit']['chunk_id']) != result['unit']:
            raise ModelError('Saved candidate payload differs from the active search units.')
    return case, saved, saved_path, units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev-case', required=True)
    parser.add_argument('--model', help='Exact API identifier of a loaded local Qwen model')
    parser.add_argument('--run', action='store_true', help='Make one local chat call after checking')
    parser.add_argument('--max-tokens', type=int, default=2048)
    parser.add_argument('--reasoning', choices=['default', 'off'], default='default',
                        help='Use default for imported models that do not expose a reasoning switch')
    args = parser.parse_args()
    models = configured_models()
    try:
        if not 256 <= args.max_tokens <= 8192:
            raise ModelError('Use max-tokens between 256 and 8192.')
        if urlparse(models.base).hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ModelError('This trial requires LM Studio on this Mac.')
        if os.getenv('LM_API_TOKEN'):
            raise ModelError('Pinned SDK token checking does not support authenticated servers.')
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case, saved, saved_path, units = load_saved_case(args.dev_case, config)
        prompt = build_prompt(saved['question'], saved['results'], saved['filters'])
        model_id = args.model or os.getenv('LM_CHAT_MODEL')
        if model_id not in ('qwen3.5-4b', 'qwen3.5-9b-mlx'):
            raise ModelError('Select qwen3.5-4b or qwen3.5-9b-mlx; this trial is local only.')
        import lmstudio as lms
        loaded = next((m for m in lms.list_loaded_models('llm')
                       if m.identifier == model_id), None)
        if loaded is None:
            raise ModelError(f'Load {model_id} in LM Studio first.')
        chat = lms.Chat(SYSTEM)
        chat.add_user_message(prompt)
        print(f'Checking full prompt with loaded model: {model_id}', flush=True)
        formatted = loaded.apply_prompt_template(chat)
        budget = check_budget(len(loaded.tokenize(formatted)),
                              loaded.get_context_length(), args.max_tokens)
        print(f'PASS: {budget["prompt_tokens"]} prompt tokens + '
              f'{args.max_tokens} output + 64 reserve fit '
              f'{budget["loaded_context_tokens"]} loaded context tokens.', flush=True)
        identity = {'case_id': args.dev_case, 'model': model_id,
                    'saved_candidates_sha256': sha(saved_path),
                    'prompt_sha256': hashlib.sha256((SYSTEM + '\n' + prompt).encode()).hexdigest(),
                    'rerank_code_sha256': sha(Path(__file__).with_name('rerank.py')),
                    'runner_code_sha256': sha(__file__),
                    'max_tokens': args.max_tokens, 'temperature': 0.2,
                    'endpoint': '/api/v1/chat', 'reasoning': args.reasoning,
                    'request_timeout_seconds': 300,
                    'store': False,
                    'budget': budget}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        output = Path('data/indexes/rerank-trial') / f'{args.dev_case}-{run_id}.json'
        if not args.run:
            check_path = output.with_name(output.stem + '-check.json')
            write_json(check_path, {'status': 'context_checked', 'identity': identity,
                                   'candidate_count': len(saved['results'])})
            print(f'SAVED: {check_path}\nNo generation, embedding, Claude calls or GitHub sync.')
            return 0
        if output.exists():
            raise ModelError(f'Trial already saved at {output}. Inspect it before repeating a model call.')
        print('Reranking twenty saved candidates locally; waiting for final JSON...', flush=True)
        record = {'status': 'started', 'identity': identity, 'question': saved['question'],
                  'filters': saved['filters'], 'input_path': str(saved_path),
                  'original_results': saved['results']}
        write_json(output, record)
        started = time.perf_counter()
        try:
            data = request_ranking(models, prompt, model_id, args.max_tokens,
                                   reasoning='off' if args.reasoning == 'off' else None)
            record.update(raw_api_response=data, usage=data.get('stats', {}),
                          rerank_seconds=time.perf_counter() - started)
            write_json(output, record)
            text = final_ranking_text(data, args.max_tokens,
                                      allow_reasoning=args.reasoning == 'default')
            record['raw_response'] = text
            results = apply_order(text, saved['results'], top_k=5)
        except Exception as error:
            record.update(status='failed', error=safe_error(error),
                          rerank_seconds=time.perf_counter() - started)
            write_json(output, record)
            raise ModelError(f'{safe_error(error)} Failure saved at {output}. '
                             'No automatic retry or silent fallback.') from None
        seconds = record['rerank_seconds']
        # Gold is consulted only after the model has returned its ordering.
        before = score_retrieval(saved['results'], case, units, k=5)
        after = score_retrieval(results, case, units, k=5)
        record.update(status='complete', results=results,
                      baseline_metrics_at_5=before, reranked_metrics_at_5=after)
        write_json(output, record)
        for result in results:
            print(f'{result["rank"]}. previously {result["pre_rerank_rank"]}: '
                  + result['unit']['chunk_id'])
        print(f'Recall@5: {before["passage_recall"]} -> {after["passage_recall"]}; '
              f'rerank seconds: {seconds:.1f}')
        print(f'SAVED: {output}\nOne development case only; no answer or holdout evaluation. '
              'No Claude calls or GitHub sync.')
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    finally:
        models.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
