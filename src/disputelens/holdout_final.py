"""Final holdout evaluation runner (holdout-final-v1). The ONLY sanctioned loader of holdout cases.

Stages (python -m disputelens.holdout_final --stage ...):
  check     verify frozen-file hashes and list unmet preconditions. Never loads holdout.
  selftest  prove this retrieval code reproduces saved development retrieval on 3 dev cases. Never loads holdout.
  retrieve  [preconditions required] load the 15 holdout cases, retrieve, build packs, score retrieval.
  count     [preconditions required] free token counts, write budget.
  run       [preconditions required] up to 15 paid Claude calls, no retries, stop after 3 consecutive failures.
  arms      offline: apply arms A, B (gate v2), C (gate v4) to the saved answers; no holdout gold used.
  report    offline: counts, latency, cost. Human review of answers is a separate step.
Protocol: eval/experiments/holdout-final-v1/protocol.json. No tuning on results.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

from .client import ModelError

PROTOCOL = Path('eval/experiments/holdout-final-v1/protocol.json')
PRECONDITIONS = Path('eval/experiments/holdout-final-v1/preconditions.json')
OUT_ROOT = Path('data/indexes/holdout-final')
SELFTEST_CASES = ('E01', 'E13', 'E22')
MAX_CALLS, MAX_USD, CONSECUTIVE_STOP = 15, 2.00, 3


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def out_dir():
    return OUT_ROOT / sha(PROTOCOL)[:24]


def frozen_status(protocol):
    return {f: (Path(f).exists() and sha(f) == h) for f, h in protocol['frozen_files_sha256'].items()}


def precondition_status(protocol):
    """Pure check of the preconditions file; returns {name: (ok, detail)}."""
    result = {}
    bad = [f for f, ok in frozen_status(protocol).items() if not ok]
    result['frozen_hashes'] = (not bad, 'all match' if not bad else 'changed: ' + ', '.join(bad))
    if not PRECONDITIONS.exists():
        for name in ('go_ahead', 'budget', 'pytest_log', 'review_plan'):
            result[name] = (False, f'{PRECONDITIONS} missing')
        return result
    p = json.loads(PRECONDITIONS.read_text())
    go = p.get('go_ahead') or {}
    result['go_ahead'] = (go.get('by') == 'Sebastian' and go.get('holdout_authorised') is True and bool(go.get('at')),
                          'explicit go-ahead recorded' if go.get('holdout_authorised') is True else 'not recorded')
    budget = p.get('budget') or {}
    result['budget'] = (budget.get('max_calls') == MAX_CALLS and isinstance(budget.get('max_usd'), (int, float))
                        and 0 < budget['max_usd'] <= MAX_USD, f'budget {budget}')
    log = Path(p.get('pytest_log') or '')
    text = log.read_text() if log.is_file() else ''
    ok = 'command_exit=0' in text[-400:] and ' passed' in text
    result['pytest_log'] = (ok, str(log) if ok else 'missing, failed or not a passing run-logged pytest log')
    result['review_plan'] = (p.get('review_plan') in ('assisted_accepted', 'independent'), f"review_plan={p.get('review_plan')}")
    return result


def require_preconditions(protocol, needed=('frozen_hashes', 'go_ahead', 'budget', 'pytest_log', 'review_plan')):
    status = precondition_status(protocol)
    missing = [f'{k}: {status[k][1]}' for k in needed if not status[k][0]]
    if missing:
        raise ModelError('Holdout preconditions not met; nothing was loaded. ' + '; '.join(missing))


def p90_nearest_rank(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


def median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ---------------------------------------------------------------- retrieval (mirrors evaluate_section_scope, hybrid)
def open_retrieval():
    """Same building blocks and settings as the development hybrid run. Needs LM Studio + local Qdrant."""
    from urllib.parse import urlparse

    from qdrant_client import QdrantClient

    from .build_index import checked_vectors
    from .client import configured_models
    from .embed_batch import loaded_embedding_model
    from .hybrid_search import fuse_rankings
    from .keyword_search import retrieve_keyword
    from .scoped_vector_search import retrieve_scoped
    from .section_scope import section_applicable

    config = json.loads(Path('data/pipeline-config.json').read_text())
    pointer = json.loads(Path('data/indexes/section-scope/hybrid-latest.json').read_text())
    directory = Path(pointer['comparison_path']).parent
    scopes = json.loads((directory / 'passage-scope-map.json').read_text())['passages']
    units = json.loads(Path(config['embedding_units_path']).read_text())['chunks']
    manifest = json.loads(Path('data/indexes/index-manifest.json').read_text())
    if manifest['status'] != 'complete' or manifest['points'] != len(units):
        raise ModelError('Active index differs from the development baseline.')
    models = configured_models()
    if urlparse(models.base).hostname not in ('localhost', '127.0.0.1', '::1') or os.getenv('LM_API_TOKEN'):
        raise ModelError('This run needs unauthenticated local LM Studio.')
    import lmstudio as lms
    prefix = os.getenv('EMBED_QUERY_PREFIX', 'search_query: ')
    if manifest['model'] != os.getenv('LM_EMBEDDING_MODEL'):
        raise ModelError('Embedding model differs from the development baseline.')
    embedder = loaded_embedding_model(lms, manifest['model'])
    context_length = embedder.get_context_length()
    client = QdrantClient(path=manifest['qdrant_path'])
    if client.count(manifest['collection_name'], exact=True).count != len(units):
        raise ModelError('Qdrant point count differs from the development baseline.')

    def compute(question, filters):
        started = time.perf_counter()
        eligible = [u for u in units if section_applicable(u, filters, scopes)]
        if len(embedder.tokenize(prefix + question)) + 8 > context_length:
            raise ModelError('Query exceeds the loaded embedding input limit.')
        vector = checked_vectors(models.embed([question], kind='query'), 1, manifest['dimension'])[0].tolist()
        vec = retrieve_scoped(client, manifest, vector, filters, eligible, scopes, 20)
        kw = retrieve_keyword(eligible, question, filters, 20)
        results = fuse_rankings(vec, kw, 20)
        if any(not section_applicable(r['unit'], filters, scopes) for r in results):
            raise ModelError('Section scope verification failed.')
        return {'results': results, 'retrieval_seconds': time.perf_counter() - started,
                'query_embedding_calls': 1, 'component_candidates': {'vector': vec, 'bm25': kw},
                'section_eligible_units': len(eligible)}

    def close():
        client.close()
        models.close()
    return compute, close, {'scopes': scopes, 'units': units, 'directory': directory, 'config': config}


def selftest():
    compute, close, ctx = open_retrieval()
    try:
        cases = {c['case_id']: c for c in json.loads(Path(ctx['config']['dev_cases_path']).read_text())}
        for cid in SELFTEST_CASES:
            case = cases[cid]
            if case['split'] != 'dev':
                raise ModelError('Selftest uses development cases only.')
            saved = json.loads((ctx['directory'] / 'cases' / f'{cid}.json').read_text())
            fresh = compute(case['question'], case['filters'])
            a = [r['unit']['chunk_id'] for r in saved['results']]
            b = [r['unit']['chunk_id'] for r in fresh['results']]
            print(f'{cid}: {"identical" if a == b else "DIFFERENT"} top-20 ranking ({len(a)} vs {len(b)})')
            if a != b:
                raise ModelError(f'{cid}: holdout retrieval path does not reproduce development retrieval; do not proceed.')
        print('SELFTEST PASSED: retrieval path reproduces saved development rankings. Holdout not loaded.')
    finally:
        close()


# ---------------------------------------------------------------- holdout stages
def load_holdout(config):
    path = Path(config['holdout_cases_path'])
    cases = json.loads(path.read_text())
    if len(cases) != 15 or any(c.get('split') != 'holdout' for c in cases):
        raise ModelError('Expected exactly 15 holdout cases.')
    return cases, sha(path)


def retrieve(protocol):
    require_preconditions(protocol)
    from .context_pack import build_context
    from .embed_batch import write_json
    from .evaluate_retrieval import query_type, score_retrieval
    compute, close, ctx = open_retrieval()
    try:
        cases, holdout_sha = load_holdout(ctx['config'])
        out = out_dir()
        write_json(out / 'holdout-identity.json', {'holdout_cases_sha256': holdout_sha, 'protocol_sha256': sha(PROTOCOL),
                                                   'loaded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        for n, case in enumerate(cases, 1):
            target = out / 'retrieval' / f"{case['case_id']}.json"
            if target.exists():
                print(f'REUSED {n}/15 {case["case_id"]}')
                continue
            result = compute(case['question'], case['filters'])
            record = {'case_id': case['case_id'], 'question': case['question'], 'filters': case['filters'],
                      'query_type': query_type(case['question']), **result,
                      'metrics': {str(k): score_retrieval(result['results'], case, ctx['units'], k) for k in (5, 20)}}
            write_json(target, record)
            pack = build_context(result['results'], case['filters'], ctx['scopes'], 6000)
            pack['question'] = case['question']
            pack['case_id'] = case['case_id']
            for key in ('trusted_settings', 'text', 'citations', 'groups', 'budget'):
                if key not in pack:
                    raise ModelError(f'Context pack lacks {key}; builder output differs from development.')
            write_json(out / 'packs' / f"{case['case_id']}.json", pack)
            print(f'SAVED {n}/15 {case["case_id"]}: pack {pack["budget"]["used"]}/6000 words')
    finally:
        close()


def prompt_for(pack):
    from .grounded_answer import SYSTEM, build_answer_prompt
    prompt = build_answer_prompt(pack['question'], pack)
    return SYSTEM, prompt, hashlib.sha256((SYSTEM + '\n' + prompt).encode()).hexdigest()


def claude_stage(protocol, stage):
    require_preconditions(protocol)
    import httpx

    from .claude_answer_trial import final_text
    from .client import configured_models
    from .embed_batch import safe_error, write_json
    from .grounded_answer import validate_answer
    from .paid_budget import reserve_paid_request, token_cost
    out = out_dir()
    pricing = json.loads(Path('data/claude-pricing.json').read_text())
    model = pricing['model']
    models = configured_models()  # loads the ignored .env before the environment check
    if os.getenv('CLAUDE_MODEL') != model or not os.getenv('ANTHROPIC_API_KEY') or model != protocol['generation']['model']:
        models.close()
        raise ModelError('Configured model or key does not match the protocol.')
    headers = {'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'}
    packs = {p.stem: json.loads(p.read_text()) for p in sorted((out / 'packs').glob('*.json'))}
    if len(packs) != 15:
        raise ModelError('Expected 15 saved holdout packs; run the retrieve stage first.')
    budget_path = out / 'budget.json'
    try:
        jobs = []
        for cid, pack in packs.items():
            system, prompt, fingerprint = prompt_for(pack)
            jobs.append((cid, pack, system, prompt, fingerprint))
        if stage == 'count':
            if budget_path.exists():
                raise ModelError('Budget already exists; do not recount automatically.')
            counted = []
            for cid, _, system, prompt, fingerprint in jobs:
                data = models._request('POST', 'https://api.anthropic.com/v1/messages/count_tokens', headers=headers,
                                       json={'model': model, 'system': system, 'messages': [{'role': 'user', 'content': prompt}]})
                n = data.get('input_tokens')
                allowance = math.ceil(n * 1.1) + 512
                counted.append({'case_id': cid, 'prompt_sha256': fingerprint, 'counted_input_tokens': n,
                                'input_token_allowance': allowance, 'reserved_usd': token_cost(allowance, 8192, pricing)})
                print(f'COUNTED {cid}: {n} input tokens', flush=True)
            total = sum(j['reserved_usd'] for j in counted)
            write_json(budget_path, {'status': 'prepared', 'identity': {'protocol_sha256': sha(PROTOCOL), 'pricing_sha256': sha('data/claude-pricing.json')},
                                     'model': model, 'pricing': pricing, 'max_calls': MAX_CALLS, 'max_usd': MAX_USD,
                                     'max_output_tokens': 8192, 'jobs': counted, 'reservations': {},
                                     'full_run_reserved_usd': total, 'full_run_fits_allowance': total <= MAX_USD})
            print(f'RESERVED MAXIMUM ${total:.4f} against cap ${MAX_USD:.2f}')
            if total > MAX_USD:
                raise ModelError('Buffered allowance exceeds the cap; no paid calls.')
            return
        budget = json.loads(budget_path.read_text())
        if budget['identity']['protocol_sha256'] != sha(PROTOCOL) or not budget['full_run_fits_allowance']:
            raise ModelError('Prepared budget does not match the protocol.')
        failures = 0
        for cid, pack, system, prompt, fingerprint in jobs:
            target = out / 'answers' / f'{cid}.json'
            if target.exists():
                print(f'SKIP {cid}: attempt already saved; no retry.')
                continue
            attempt_id = hashlib.sha256((cid + fingerprint + model).encode()).hexdigest()[:24]
            reserve_paid_request(budget_path, attempt_id, fingerprint, model, 8192)
            record = {'status': 'started', 'case_id': cid, 'model': model, 'prompt_sha256': fingerprint, 'max_tokens': 8192}
            write_json(target, record)
            started = time.perf_counter()
            print(f'GENERATING {cid}: one call; no retry.', flush=True)
            try:
                data = models._request('POST', 'https://api.anthropic.com/v1/messages', headers=headers,
                                       timeout=httpx.Timeout(300, connect=5),
                                       json={'model': model, 'max_tokens': 8192, 'system': system,
                                             'messages': [{'role': 'user', 'content': prompt}]})
                usage = data.get('usage', {})
                record.update(raw_api_response=data, usage=usage, generation_seconds=time.perf_counter() - started)
                if usage.get('input_tokens') is not None and usage.get('output_tokens') is not None:
                    record['calculated_api_cost_usd'] = token_cost(usage['input_tokens'], usage['output_tokens'], pricing)
                text = final_text(data)
                record['raw_response'] = text
                checked = validate_answer(text, pack)
                record.update(status='complete_requires_review', **checked)
                failures = 0
            except Exception as error:
                record.update(status='failed', error=safe_error(error), generation_seconds=time.perf_counter() - started)
                failures += 1
            write_json(target, record)
            print(f'{cid}: {record["status"]} in {record["generation_seconds"]:.1f}s', flush=True)
            if failures >= CONSECUTIVE_STOP:
                raise ModelError('Three consecutive failures: stopping without retries.')
    finally:
        models.close()


# ---------------------------------------------------------------- offline post-processing
def case_like(pack, answer):
    return {'case_id': pack.get('case_id', ''), 'question': pack['question'], 'frozen_context_pack': pack,
            'answer': answer, 'saved_status': 'citation_valid_requires_review'}


def apply_arms(pack, answer):
    """Arms B and C on one validated answer. Returns outputs and audit records."""
    from .scope_gate import gate
    case = case_like(pack, answer)
    b, audit_b = gate(case, answer, 2)
    c, audit_c = gate(case, answer, 4)
    return {'A_baseline': answer, 'B_gate_v2': b, 'C_gate_v4': c}, {
        'B': audit_b['action'], 'C': audit_c['action'],
        'B_withheld_words': audit_b.get('withheld_words', 0), 'C_withheld_words': audit_c.get('withheld_words', 0)}


def arms():
    out = out_dir()
    packs = {p.stem: json.loads(p.read_text()) for p in sorted((out / 'packs').glob('*.json'))}
    rows = {}
    for path in sorted((out / 'answers').glob('*.json')):
        record = json.loads(path.read_text())
        if record['status'] != 'complete_requires_review':
            rows[record['case_id']] = {'status': record['status']}
            continue
        outputs, audit = apply_arms(packs[record['case_id']], record['answer'])
        (out / 'arms').mkdir(exist_ok=True)
        (out / 'arms' / f"{record['case_id']}.json").write_text(json.dumps(outputs, indent=2))
        rows[record['case_id']] = {'status': 'valid', **audit}
    counts = {'B': {}, 'C': {}}
    for r in rows.values():
        if r.get('status') == 'valid':
            for k in ('B', 'C'):
                counts[k][r[k]] = counts[k].get(r[k], 0) + 1
    (out / 'arms-summary.json').write_text(json.dumps({'cases': rows, 'counts': counts}, indent=2))
    print(json.dumps(counts, indent=1))


def report():
    out = out_dir()
    answers = [json.loads(p.read_text()) for p in sorted((out / 'answers').glob('*.json'))]
    valid = [a for a in answers if a['status'] == 'complete_requires_review']
    seconds = [a['generation_seconds'] for a in answers if 'generation_seconds' in a]
    cost = [a['calculated_api_cost_usd'] for a in answers if 'calculated_api_cost_usd' in a]
    retrieval = list((out / 'retrieval').glob('*.json'))
    summary = {'attempted': len(answers), 'structurally_valid': len(valid), 'failed': len(answers) - len(valid),
               'P4_at_least_12_valid': len(valid) >= 12,
               'latency_seconds': {'n': len(seconds), 'median': median(seconds), 'p90_nearest_rank': p90_nearest_rank(seconds)},
               'api_cost_usd_known': round(sum(cost), 6), 'cost_known_for': len(cost), 'retrieval_cases': len(retrieval),
               'note': 'P1, P2 and P3 require human review of the answers and arm outputs; they are not computed here.'}
    (out / 'report.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('check', 'selftest', 'retrieve', 'count', 'run', 'arms', 'report'), default='check')
    stage = parser.parse_args().stage
    try:
        protocol = json.loads(PROTOCOL.read_text())
        if stage == 'check':
            for name, (ok, detail) in precondition_status(protocol).items():
                print(f'{"OK     " if ok else "MISSING"} {name}: {detail}')
            print('Holdout not loaded.')
        elif stage == 'selftest':
            selftest()
        elif stage == 'retrieve':
            retrieve(protocol)
        elif stage in ('count', 'run'):
            claude_stage(protocol, stage)
        elif stage == 'arms':
            arms()
        else:
            report()
    except Exception as error:
        print('STOP: ' + str(error)[:400], file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
