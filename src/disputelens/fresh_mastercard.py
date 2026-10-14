"""Fresh Mastercard answer set (mastercard-fresh-v1). Protocol: eval/experiments/mastercard-fresh-v1/protocol.json.

Stages: check, attach-tests, retrieve, count, run, detectors, packet, score, report.
Reuses holdout_final retrieval and prompt code unchanged. No tuning after results.
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
from .holdout_final import median, open_retrieval, p90_nearest_rank, prompt_for

FOLDER = Path('eval/experiments/mastercard-fresh-v1')
PROTOCOL = FOLDER / 'protocol.json'
PRECONDITIONS = FOLDER / 'preconditions.json'
CASES = Path('eval/fresh/mastercard-fresh-v1/cases.json')
OUT_ROOT = Path('data/indexes/mastercard-fresh')
MAX_CALLS, MAX_USD, CONSECUTIVE_STOP, MAX_OUT = 12, 1.00, 3, 4096


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def out_dir():
    return OUT_ROOT / sha(PROTOCOL)[:24]


def preconditions(protocol):
    bad = [f for f, h in protocol['frozen_files_sha256'].items() if not Path(f).exists() or sha(f) != h]
    res = {'frozen_hashes': (not bad, 'all match' if not bad else 'changed: ' + ', '.join(bad))}
    if not PRECONDITIONS.exists():
        for k in ('go_ahead', 'budget', 'pytest_log', 'review_plan'):
            res[k] = (False, f'{PRECONDITIONS} missing')
        return res
    p = json.loads(PRECONDITIONS.read_text())
    go = p.get('go_ahead') or {}
    res['go_ahead'] = (go.get('by') == 'Sebastian' and go.get('authorised') is True and bool(go.get('at')) and bool(go.get('words')),
                       'recorded' if go.get('authorised') is True else 'not recorded')
    b = p.get('budget') or {}
    res['budget'] = (b.get('max_calls') == MAX_CALLS and isinstance(b.get('max_usd'), (int, float)) and 0 < b['max_usd'] <= MAX_USD, f'budget {b}')
    log = Path(p.get('pytest_log') or '')
    text = log.read_text() if log.is_file() else ''
    res['pytest_log'] = ('command_exit=0' in text[-400:] and ' passed' in text, str(log) if log.is_file() else 'missing')
    res['review_plan'] = (p.get('review_plan') == 'independent', f"review_plan={p.get('review_plan')}")
    return res


def require(protocol, needed=('frozen_hashes', 'go_ahead', 'budget', 'pytest_log')):
    st = preconditions(protocol)
    missing = [f'{k}: {st[k][1]}' for k in needed if not st[k][0]]
    if missing:
        raise ModelError('Preconditions not met; nothing was run. ' + '; '.join(missing))


def attach_tests(log):
    text = Path(log).read_text() if Path(log).is_file() else ''
    if not ('command_exit=0' in text[-400:] and ' passed' in text):
        raise ModelError('That log is not a passing run-logged pytest run.')
    p = json.loads(PRECONDITIONS.read_text())
    p['pytest_log'] = str(log)
    PRECONDITIONS.write_text(json.dumps(p, indent=2))
    print('Attached', log)


def load_cases():
    cases = json.loads(CASES.read_text())
    if len(cases) != 12 or len({c['case_id'] for c in cases}) != 12 or any(c['filters']['scheme'] != 'Mastercard' for c in cases):
        raise ModelError('Expected 12 unique Mastercard cases.')
    return cases


def retrieve(protocol):
    require(protocol, ('frozen_hashes', 'go_ahead', 'budget'))
    from .context_pack import build_context
    from .embed_batch import write_json
    compute, close, ctx = open_retrieval()
    try:
        out = out_dir()
        for n, case in enumerate(load_cases(), 1):
            if (out / 'packs' / f"{case['case_id']}.json").exists():
                print(f'REUSED {case["case_id"]}')
                continue
            result = compute(case['question'], case['filters'])
            write_json(out / 'retrieval' / f"{case['case_id']}.json", {'case_id': case['case_id'], 'question': case['question'], **result})
            pack = build_context(result['results'], case['filters'], ctx['scopes'], 6000)
            pack['question'], pack['case_id'] = case['question'], case['case_id']
            write_json(out / 'packs' / f"{case['case_id']}.json", pack)
            print(f'SAVED {n}/12 {case["case_id"]}: pack {pack["budget"]["used"]}/6000 words')
    finally:
        close()


def claude_stage(protocol, stage):
    require(protocol)
    import httpx

    from .claude_answer_trial import final_text
    from .client import configured_models
    from .embed_batch import safe_error, write_json
    from .grounded_answer import validate_answer
    from .paid_budget import reserve_paid_request, token_cost
    out = out_dir()
    pricing = json.loads(Path('data/claude-pricing.json').read_text())
    model = pricing['model']
    models = configured_models()
    if os.getenv('CLAUDE_MODEL') != model or not os.getenv('ANTHROPIC_API_KEY') or model != protocol['generation']['model']:
        models.close()
        raise ModelError('Configured model or key does not match the protocol.')
    headers = {'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'}
    packs = {p.stem: json.loads(p.read_text()) for p in sorted((out / 'packs').glob('*.json'))}
    if len(packs) != 12:
        models.close()
        raise ModelError('Expected 12 saved packs; run the retrieve stage first.')
    budget_path = out / 'budget.json'
    try:
        jobs = [(cid, pack, *prompt_for(pack)) for cid, pack in packs.items()]
        if stage == 'count':
            if budget_path.exists():
                raise ModelError('Budget already exists; do not recount automatically.')
            counted = []
            for cid, _, system, prompt, fp in jobs:
                data = models._request('POST', 'https://api.anthropic.com/v1/messages/count_tokens', headers=headers,
                                       json={'model': model, 'system': system, 'messages': [{'role': 'user', 'content': prompt}]})
                n = data.get('input_tokens')
                allowance = math.ceil(n * 1.1) + 512
                counted.append({'case_id': cid, 'prompt_sha256': fp, 'counted_input_tokens': n, 'input_token_allowance': allowance,
                                'reserved_usd': token_cost(allowance, MAX_OUT, pricing)})
                print(f'COUNTED {cid}: {n} input tokens', flush=True)
            total = sum(j['reserved_usd'] for j in counted)
            write_json(budget_path, {'status': 'prepared', 'identity': {'protocol_sha256': sha(PROTOCOL), 'pricing_sha256': sha('data/claude-pricing.json')},
                                     'model': model, 'pricing': pricing, 'max_calls': MAX_CALLS, 'max_usd': MAX_USD, 'max_output_tokens': MAX_OUT,
                                     'jobs': counted, 'reservations': {}, 'full_run_reserved_usd': total, 'full_run_fits_allowance': total <= MAX_USD})
            print(f'RESERVED MAXIMUM ${total:.4f} against cap ${MAX_USD:.2f}')
            if total > MAX_USD:
                raise ModelError('Buffered allowance exceeds the cap; no paid calls.')
            return
        budget = json.loads(budget_path.read_text())
        if budget['identity']['protocol_sha256'] != sha(PROTOCOL) or not budget['full_run_fits_allowance']:
            raise ModelError('Prepared budget does not match the protocol.')
        failures = 0
        for cid, pack, system, prompt, fp in jobs:
            target = out / 'answers' / f'{cid}.json'
            if target.exists():
                print(f'SKIP {cid}: attempt already saved; no retry.')
                continue
            reserve_paid_request(budget_path, hashlib.sha256((cid + fp + model).encode()).hexdigest()[:24], fp, model, MAX_OUT)
            record = {'status': 'started', 'case_id': cid, 'model': model, 'prompt_sha256': fp, 'max_tokens': MAX_OUT}
            write_json(target, record)
            started = time.perf_counter()
            print(f'GENERATING {cid}: one call; no retry.', flush=True)
            try:
                data = models._request('POST', 'https://api.anthropic.com/v1/messages', headers=headers, timeout=httpx.Timeout(300, connect=5),
                                       json={'model': model, 'max_tokens': MAX_OUT, 'system': system, 'messages': [{'role': 'user', 'content': prompt}]})
                usage = data.get('usage', {})
                record.update(raw_api_response=data, usage=usage, generation_seconds=time.perf_counter() - started)
                if usage.get('input_tokens') is not None and usage.get('output_tokens') is not None:
                    record['calculated_api_cost_usd'] = token_cost(usage['input_tokens'], usage['output_tokens'], pricing)
                text = final_text(data)
                record['raw_response'] = text
                record.update(status='complete_requires_review', **validate_answer(text, pack))
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


# ------------------------------------------------------------------ offline analysis
def valid_answers():
    out = out_dir()
    packs = {p.stem: json.loads(p.read_text()) for p in (out / 'packs').glob('*.json')}
    rows = []
    for path in sorted((out / 'answers').glob('*.json')):
        rec = json.loads(path.read_text())
        if rec['status'] == 'complete_requires_review':
            rows.append((rec['case_id'], packs[rec['case_id']], rec['answer']))
    return rows


def claim_flags(question, pack, answer, semantic):
    """Per claim: does v2 flag any cited passage; does the semantic detector. semantic=(pick, best, sim, margin) or None."""
    from .scope_detector import unestablished
    from .scope_detector_semantic import clean, decide, is_established
    index = {e['citation_id']: e for g in pack['groups'] for e in g['evidence']}
    rows = []
    for n, claim in enumerate(answer['claims'], 1):
        v2 = sem = False
        for c in claim['citations']:
            h = index[c['id']]['headings']
            base = unestablished(h, question, 2)
            v2 = v2 or bool(base)
            if semantic and base:
                pick, best, sim, margin = semantic
                est = len(h) >= 4 and is_established(clean(h[3]), best, sim, margin, pick['tau'], pick['delta'])
                sem = sem or bool(decide(base, est))
            elif base:
                sem = True
        rows.append({'claim': n, 'text': claim['text'], 'cited': [c['id'] for c in claim['citations']], 'v2': v2, 'semantic': sem})
    return rows


def detectors():
    from .context_pack import build_context  # noqa: F401  (import check only)
    from .scope_detector_semantic import FOLDER as SEM, Embedder, nearest, setup
    from .holdout_final import case_like
    from .scope_gate import gate
    pick = json.loads((SEM / 'chosen.json').read_text())['chosen']
    emb = Embedder()
    titles, tv = setup(emb)
    table, cases_out = [], {}
    for cid, pack, answer in valid_answers():
        q = pack['question']
        best, sim, margin = nearest(emb.vectors([q], 'query')[0], tv, titles)
        flags = claim_flags(q, pack, answer, (pick, best, sim, margin))
        case = case_like(pack, answer)
        b, ab = gate(case, answer, 2)
        c, ac = gate(case, answer, 4)
        cases_out[cid] = {'question': q, 'nearest_title': best, 'sim': round(sim, 4), 'margin': round(margin, 4),
                          'gate_v2_action': ab['action'], 'gate_v4_action': ac['action'], 'claims': flags}
        table += [{'case': cid, **f} for f in flags]
    (out_dir() / 'detectors.json').write_text(json.dumps(cases_out, indent=2))
    n = len(table)
    agree = {'both_flag': sum(r['v2'] and r['semantic'] for r in table), 'v2_only': sum(r['v2'] and not r['semantic'] for r in table),
             'semantic_only': sum(r['semantic'] and not r['v2'] for r in table), 'neither': sum(not r['v2'] and not r['semantic'] for r in table)}
    print(json.dumps({'claims': n, 'agreement': agree,
                      'gate_actions': {cid: (v['gate_v2_action'], v['gate_v4_action']) for cid, v in cases_out.items()}}, indent=1))


def packet():
    """Reviewer packet WITHOUT detector flags, plus a key file with them."""
    det = json.loads((out_dir() / 'detectors.json').read_text())
    lines = ['# Claim rating packet (mastercard-fresh-v1)', '',
             'For each claim, rate whether it applies to the situation in the question: yes, no, or unsure.',
             'A claim applies if a merchant in exactly that situation could rely on it. Rate "no" if it only holds for a different',
             'reason code, region, card scheme, program or subtype than the question describes.', '']
    for cid, pack, answer in valid_answers():
        index = {e['citation_id']: e for g in pack['groups'] for e in g['evidence']}
        lines += [f'## {cid}', '', f'**Question:** {pack["question"]}', '']
        for n, claim in enumerate(answer['claims'], 1):
            lines += [f'**Claim {n}:** {claim["text"]}', '']
            for c in claim['citations']:
                lines += [f'- Cited section: {" > ".join(index[c["id"]]["headings"][1:])}', f'  - Quote: "{c["quote"]}"']
            lines += ['', f'Rating {cid}-{n}: ______', '']
    (FOLDER / 'rating-packet.md').write_text('\n'.join(lines))
    (FOLDER / 'packet-key.json').write_text(json.dumps(det, indent=2))
    print('Wrote', FOLDER / 'rating-packet.md', '(no detector flags in it)')


def score_rows(rows, labels):
    """rows: [{case, claim, v2, semantic}]; labels: {case: [yes|no|unsure, ...]}. Pure."""
    res = {}
    for name in ('v2', 'semantic'):
        r = {'wrong_caught': 0, 'wrong_missed': 0, 'applies_flagged': 0, 'applies_not_flagged': 0, 'unsure': 0}
        for row in rows:
            lab = labels[row['case']][row['claim'] - 1]
            if lab == 'unsure':
                r['unsure'] += 1
            elif lab == 'no':
                r['wrong_caught' if row[name] else 'wrong_missed'] += 1
            else:
                r['applies_flagged' if row[name] else 'applies_not_flagged'] += 1
        res[name] = r
    wrong = res['v2']['wrong_caught'] + res['v2']['wrong_missed']
    v2_needless, sem_needless = res['v2']['applies_flagged'], res['semantic']['applies_flagged']
    safe = res['semantic']['wrong_missed'] <= res['v2']['wrong_missed'] and res['semantic']['wrong_caught'] >= res['v2']['wrong_caught']
    fewer = v2_needless > 0 and (v2_needless - sem_needless) / v2_needless >= 0.25
    res['wrong_scope_claims'] = wrong
    res['decision'] = ('inconclusive_on_safety' if wrong < 3 else
                       'semantic_is_a_shipping_candidate' if safe and fewer else 'v2_stays_default')
    res['detail'] = {'semantic_misses_nothing_v2_catches': safe, 'needless_flag_reduction_25pct': fewer}
    return res


def score(labels_path):
    data = json.loads(Path(labels_path).read_text())
    if data.get('independent') is not True or not data.get('labeller'):
        raise ModelError('Labels must come from a named independent labeller (independent: true).')
    det = json.loads((out_dir() / 'detectors.json').read_text())
    rows = [{'case': cid, **c} for cid, v in det.items() for c in v['claims']]
    for cid, v in det.items():
        if len(data['ratings'].get(cid, [])) != len(v['claims']) or any(x not in ('yes', 'no', 'unsure') for x in data['ratings'][cid]):
            raise ModelError(f'Ratings for {cid} are missing or malformed.')
    result = score_rows(rows, data['ratings'])
    result['labels_sha256'] = sha(labels_path)
    result['protocol_sha256'] = sha(PROTOCOL)
    (FOLDER / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


def report():
    out = out_dir()
    answers = [json.loads(p.read_text()) for p in sorted((out / 'answers').glob('*.json'))]
    valid = [a for a in answers if a['status'] == 'complete_requires_review']
    secs = [a['generation_seconds'] for a in answers if 'generation_seconds' in a]
    cost = [a['calculated_api_cost_usd'] for a in answers if 'calculated_api_cost_usd' in a]
    summary = {'attempted': len(answers), 'valid': len(valid), 'G1_at_least_10_valid': len(valid) >= 10,
               'api_cost_usd_known': round(sum(cost), 6), 'G2_within_cap': sum(cost) <= MAX_USD and len(answers) <= MAX_CALLS,
               'latency_seconds': {'median': median(secs), 'p90_nearest_rank': p90_nearest_rank(secs)},
               'statuses': {a['case_id']: a['status'] for a in answers}}
    (out / 'report.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=('check', 'attach-tests', 'retrieve', 'count', 'run', 'detectors', 'packet', 'score', 'report'))
    parser.add_argument('--log')
    parser.add_argument('--labels')
    a = parser.parse_args()
    try:
        protocol = json.loads(PROTOCOL.read_text())
        if a.stage == 'check':
            for k, (ok, d) in preconditions(protocol).items():
                print(f'{"OK     " if ok else "MISSING"} {k}: {d}')
        elif a.stage == 'attach-tests':
            attach_tests(a.log)
        elif a.stage == 'retrieve':
            retrieve(protocol)
        elif a.stage in ('count', 'run'):
            claude_stage(protocol, a.stage)
        elif a.stage == 'detectors':
            detectors()
        elif a.stage == 'packet':
            packet()
        elif a.stage == 'score':
            score(a.labels)
        else:
            report()
    except Exception as error:
        print('STOP: ' + str(error)[:400], file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
