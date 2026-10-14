"""Deterministic scope gate on a generated answer. Offline; no model call.

Rule and thresholds are fixed in eval/experiments/scope-gate-v1/protocol.json.
"""
import copy
import hashlib
import json
from pathlib import Path

from .grounded_answer import validate_answer
from .scope_detector import BUNDLE, unestablished

PROTOCOL = Path('eval/experiments/scope-gate-v1/protocol.json')
ATTEMPT = Path('data/indexes/flagged-answer-trial/634d43ae4d6ad7e164c1c684/E22-claude-attempt.json')
PREFIX = 'Only if this applies to you ({q}): '
PREFIX2 = 'Only if your dispute is {t}: '
ASK2 = ('Your question does not say which type of dispute this is. The rules I found apply only to specific '
        'disputes, for example: {t}. Which reason code or dispute type is your chargeback?')


def flagged_map(case):
    return {e['citation_id']: unestablished(e['headings'], case['question'], 2)
            for g in case['frozen_context_pack']['groups'] for e in g['evidence']
            if unestablished(e['headings'], case['question'], 2)}


def describe(qualifiers):
    return ', '.join(sorted(qualifiers))


def titles(case, ids):
    """v2: deepest heading below chapter that carries a flagged code or phrase, per cited flagged passage."""
    index = {e['citation_id']: e for g in case['frozen_context_pack']['groups'] for e in g['evidence']}
    found = []
    for cid in ids:
        qualifiers = unestablished(index[cid]['headings'], case['question'], 2)
        for heading in reversed(index[cid]['headings'][2:]):
            clean = ' '.join(heading.split())
            if any(q in clean.lower() for q in qualifiers):
                found.append(clean)
                break
    return found


def ranked(found, limit):
    counts = {}
    for t in found:
        counts[t] = counts.get(t, 0) + 1
    return sorted(counts, key=lambda t: (-counts[t], t))[:limit]


NOTE3 = 'The guide gives this same wording in {n} reason-code sections; check your own reason code for additional conditions.'


def gate(case, answer, version=1):
    flagged = flagged_map(case)
    marks, exempt = [], []
    for claim in answer.get('claims', []):
        q = sorted({x for c in claim['citations'] for x in flagged.get(c['id'], [])})
        if version == 3 and q:
            from .scope_invariance import is_invariant, match
            quotes = [c['quote'] for c in claim['citations'] if c['id'] in flagged]
            if all(is_invariant(x) for x in quotes):
                exempt.append(min(match(x)['sections'] for x in quotes))
                q = []
        elif version == 4 and q:
            from .scope_invariance import claim_invariant
            quotes = [c['quote'] for c in claim['citations'] if c['id'] in flagged]
            ok, reports = claim_invariant(quotes)
            if ok:
                exempt.append(min(r['sections'] for r in reports))
                q = []
        marks.append(q)
    version_wording = 2 if version >= 3 else version
    if not any(marks):
        if exempt:
            out = copy.deepcopy(answer)
            out['status'] = 'partial' if out['status'] == 'answered' else out['status']
            out['missing_information'] = list(out['missing_information']) + [NOTE3.format(n=min(exempt))]
            return out, {'action': 'invariant_note', 'withheld_claims': 0, 'withheld_words': 0}
        return answer, {'action': 'unchanged', 'withheld_claims': 0, 'withheld_words': 0}
    union = sorted({x for q in marks for x in q})
    ask = ('Your question does not establish which scope applies. The matching rules found apply only under: '
           f'{describe(union)}. Which reason code or program applies to your dispute?')
    cited = {c['id'] for claim, q in zip(answer['claims'], marks) if q for c in claim['citations'] if c['id'] in flagged}
    if version_wording == 2:
        ask = ASK2.format(t='; '.join(ranked(titles(case, sorted(cited)), 3)))
    out = copy.deepcopy(answer)
    if all(marks):
        audit = {'action': 'fail_closed', 'withheld_claims': len(marks),
                 'withheld_words': sum(len(c['text'].split()) for c in answer['claims']),
                 'withheld': answer['claims']}
        out.update(status='needs_clarification', claims=[], missing_information=[ask])
        return out, audit
    moved = 0
    for claim, q, original in zip(out['claims'], marks, answer['claims']):
        if q:
            if version_wording == 2:
                ids = sorted({c['id'] for c in original['citations'] if c['id'] in flagged})
                prefix = PREFIX2.format(t=ranked(titles(case, ids), 1)[0])
            else:
                prefix = PREFIX.format(q=describe(q))
            claim['text'] = prefix + claim['text']
            moved += len(claim['text'].split())
    out['status'] = 'partial' if out['status'] == 'answered' else out['status']
    out['missing_information'] = list(out['missing_information']) + [ask] + ([NOTE3.format(n=min(exempt))] if exempt else [])
    return out, {'action': 'conditionalised', 'withheld_claims': sum(1 for q in marks if q), 'withheld_words': moved}


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def evaluate(cases):
    results, changed, g1, g4, g5 = {}, [], True, True, True
    inputs = [(c['case_id'], c, c['answer']) for c in cases if c['saved_status'] == 'citation_valid_requires_review']
    e22 = next(c for c in cases if c['case_id'] == 'E22')
    new_answer = json.loads(ATTEMPT.read_text())['answer']
    inputs.append(('E22-flagged-answer-v1', e22, new_answer))
    for name, case, answer in inputs:
        out, audit = gate(case, answer)
        again, _ = gate(case, answer)
        g5 &= digest(out) == digest(again)
        flagged = flagged_map(case)
        for claim in out['claims']:
            if any(c['id'] in flagged for c in claim['citations']) and not claim['text'].startswith('Only if this applies to you'):
                g1 = False
        if audit['action'] == 'unchanged':
            if out is not answer and digest(out) != digest(answer):
                g1 = False
        else:
            changed.append(name)
        try:
            validate_answer(json.dumps(out), case['frozen_context_pack'])
        except Exception as error:
            g4 = False
            audit['validation_error'] = str(error)[:200]
        results[name] = {k: v for k, v in audit.items() if k != 'withheld'}
        results[name]['status_after'] = out['status']
        results[name]['unconditional_claims_after'] = sum(1 for c in out['claims'] if not c['text'].startswith('Only if this applies'))
    baseline_changed = sorted(n for n in changed if n != 'E22-flagged-answer-v1')
    g2 = baseline_changed == ['E13', 'E22']
    e13 = results['E13']
    g3 = (e13['action'] == 'conditionalised' and e13['unconditional_claims_after'] >= 1
          and results['E22']['status_after'] == 'needs_clarification'
          and results['E22-flagged-answer-v1']['status_after'] == 'needs_clarification')
    verdict = {'G1': g1, 'G2': g2, 'G3': g3, 'G4': g4, 'G5': g5}
    verdict['overall_pass'] = all(verdict.values())
    return {'results': {k: v for k, v in results.items() if v['action'] != 'unchanged'},
            'unchanged_count': sum(1 for v in results.values() if v['action'] == 'unchanged'),
            'verdict': verdict}


PROTOCOL2 = Path('eval/experiments/scope-gate-v2/protocol.json')
PROTOCOL3 = Path('eval/experiments/scope-invariance-v1/protocol.json')
PROTOCOL4 = Path('eval/experiments/scope-invariance-v2/protocol.json')


def evaluate_v4(cases):
    from .scope_invariance import claim_invariant, following, quote_report, repeated_set, stability
    by_id = {c['case_id']: c for c in cases}
    e22, e13 = by_id['E22'], by_id['E13']
    attempt = json.loads(ATTEMPT.read_text())['answer']
    f22, f13 = flagged_map(e22), flagged_map(e13)

    def rows(case, answer, flagged):
        out = []
        for n, claim in enumerate(answer['claims'], 1):
            quotes = [c['quote'] for c in claim['citations'] if c['id'] in flagged]
            ok, reports = claim_invariant(quotes)
            out.append({'claim': n, 'flagged_quotes': len(quotes), 'claim_invariant': ok, 'quotes': reports})
        return out
    r22, r13, rn = rows(e22, e22['answer'], f22), rows(e13, e13['answer'], f13), rows(e22, attempt, f22)
    j1 = all(r['claim_invariant'] for r in r22[:3])
    out2, _ = gate(e13, e13['answer'], 2)
    out4, _ = gate(e13, e13['answer'], 4)
    j2 = all(not r['claim_invariant'] for r in r13[1:]) and digest(out2) == digest(out4)
    rep = repeated_set()
    stable = [r for r in rep if r['context_stable']]
    j3 = bool(stable) and len(stable) < len(rep)
    j4 = True
    for c in cases:
        if c['saved_status'] != 'citation_valid_requires_review' or c['case_id'] in ('E13', 'E22'):
            continue
        o, a = gate(c, c['answer'], 4)
        j4 &= a['action'] == 'unchanged' and digest(o) == digest(c['answer'])
    reported = {}
    for name, case, answer in (('E22', e22, e22['answer']), ('E22-flagged-answer-v1', e22, attempt)):
        o2, a2 = gate(case, answer, 2)
        o4, a4 = gate(case, answer, 4)
        try:
            validate_answer(json.dumps(o4), case['frozen_context_pack'])
            valid = True
        except Exception:
            valid = False
        j4 &= valid and digest(o4) == digest(gate(case, answer, 4)[0])
        kept = [c for c in o4['claims'] if not c['text'].startswith('Only if')]
        reported[name] = {'v2_action': a2['action'], 'v4_action': a4['action'], 'v4_status': o4['status'],
                          'claims_kept_unprefixed': len(kept), 'claims_of': len(answer['claims']),
                          'words_kept_that_v2_withheld': sum(len(c['text'].split()) for c in kept) if a2['action'] == 'fail_closed' else 0}
    rule = 'the issuer must not continue the dispute for the refunded amount as the refund resolved the chargeback.'
    follow = following(rule)
    share, modal = stability(follow)
    differing = [{'path': [h[:50] for h in p[1:]], 'following': t[:120]} for p, _, t in follow if t != modal]
    verdict = {'J1': j1, 'J2': j2, 'J3': j3, 'J4': j4}
    verdict['overall_pass'] = all(verdict.values())
    return {'E22_baseline': r22, 'E13': r13, 'E22_attempt': rn,
            'repeated_set': {'size': len(rep), 'context_stable': len(stable), 'rejected': len(rep) - len(stable),
                             'rejected_examples': [r['sentence'] for r in rep if not r['context_stable']][:5]},
            'refund_rule_following': {'sections': len(follow), 'modal': modal, 'modal_share': round(share, 3),
                                      'differing_sections': differing},
            'reported': reported, 'verdict': verdict}


def main_v4():
    text = PROTOCOL4.read_text()
    result = evaluate_v4(json.loads(BUNDLE.read_text())['cases'])
    result['protocol_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    (PROTOCOL4.parent / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


def evaluate_v3(cases):
    from .scope_invariance import is_invariant, match
    by_id = {c['case_id']: c for c in cases}
    e22, e13 = by_id['E22'], by_id['E13']
    attempt = json.loads(ATTEMPT.read_text())['answer']
    flagged22, flagged13 = flagged_map(e22), flagged_map(e13)

    def per_claim(case, answer, flagged):
        rows = []
        for n, claim in enumerate(answer['claims'], 1):
            quotes = [(c['id'], c['quote']) for c in claim['citations'] if c['id'] in flagged]
            rows.append({'claim': n, 'text': claim['text'][:70],
                         'quotes': [{'id': i, 'quote': q[:60], **match(q), 'invariant': is_invariant(q)} for i, q in quotes],
                         'claim_invariant': bool(quotes) and all(is_invariant(q) for _, q in quotes)})
        return rows
    rows22, rows13, rows_new = per_claim(e22, e22['answer'], flagged22), per_claim(e13, e13['answer'], flagged13), per_claim(e22, attempt, flagged22)
    i1 = all(r['claim_invariant'] for r in rows22[:3])
    i2 = all(not q['invariant'] and q['sections'] <= 3 for r in rows13 for q in r['quotes'])
    control = 'Mainland China Customer, a domestic Fee Collection must be processed as'
    i3 = match(control)['sections'] <= 3 and not is_invariant(control)
    i4, same13 = True, True
    out13_v2, _ = gate(e13, e13['answer'], 2)
    out13_v3, _ = gate(e13, e13['answer'], 3)
    same13 = digest(out13_v2) == digest(out13_v3)
    for c in cases:
        if c['saved_status'] != 'citation_valid_requires_review' or c['case_id'] in ('E13', 'E22'):
            continue
        o, a = gate(c, c['answer'], 3)
        i4 &= a['action'] == 'unchanged' and digest(o) == digest(c['answer'])
    reported = {}
    for name, case, answer in (('E22', e22, e22['answer']), ('E22-flagged-answer-v1', e22, attempt)):
        o2, a2 = gate(case, answer, 2)
        o3, a3 = gate(case, answer, 3)
        try:
            validate_answer(json.dumps(o3), case['frozen_context_pack'])
            valid = True
        except Exception:
            valid = False
        i4 &= valid and digest(o3) == digest(gate(case, answer, 3)[0])
        reported[name] = {'v2_action': a2['action'], 'v3_action': a3['action'], 'v3_status': o3['status'],
                          'v3_claims_kept_unprefixed': sum(1 for c in o3['claims'] if not c['text'].startswith('Only if')),
                          'v3_claims_of': len(answer['claims']), 'v3_note': o3['missing_information'][-1] if o3['missing_information'] else None,
                          'v3_valid': valid}
    i4 &= same13
    verdict = {'I1': i1, 'I2': i2, 'I3': i3, 'I4': i4}
    verdict['overall_pass'] = all(verdict.values())
    return {'E22_baseline_claims': rows22, 'E13_claims': rows13, 'E22_attempt_claims': rows_new,
            'negative_control': {'quote': control, **match(control)}, 'E13_v3_equals_v2': same13,
            'reported': reported, 'verdict': verdict}


def main_v3():
    text = PROTOCOL3.read_text()
    result = evaluate_v3(json.loads(BUNDLE.read_text())['cases'])
    result['protocol_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    (PROTOCOL3.parent / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


def evaluate_v2(cases):
    import re
    inputs = [(c['case_id'], c, c['answer']) for c in cases if c['saved_status'] == 'citation_valid_requires_review']
    e22 = next(c for c in cases if c['case_id'] == 'E22')
    inputs.append(('E22-flagged-answer-v1', e22, json.loads(ATTEMPT.read_text())['answer']))
    w1 = w2 = w3 = w4 = w5 = True
    shown = {}
    for name, case, answer in inputs:
        o1, a1 = gate(case, answer, 1)
        o2, a2 = gate(case, answer, 2)
        o2b, _ = gate(case, answer, 2)
        w4 &= digest(o2) == digest(o2b)
        same = (a1['action'] == a2['action'] and a1['withheld_claims'] == a2['withheld_claims'] and o1['status'] == o2['status']
                and len(o1['claims']) == len(o2['claims']) and [c['citations'] for c in o1['claims']] == [c['citations'] for c in o2['claims']])
        w1 &= same and (a1['action'] != 'unchanged' or digest(o2) == digest(answer))
        if a2['action'] == 'unchanged':
            continue
        flagged = flagged_map(case)
        ids = sorted({c['id'] for cl in answer['claims'] for c in cl['citations'] if c['id'] in flagged})
        allowed = {' '.join(h.split()) for i in ids for e in [x for g in case['frozen_context_pack']['groups'] for x in g['evidence'] if x['citation_id'] == i] for h in e['headings']}
        emitted = []
        for claim in o2['claims']:
            if claim['text'].startswith('Only if your dispute is '):
                emitted.append(claim['text'].split(': ', 1)[0][len('Only if your dispute is '):])
        ask = o2['missing_information'][-1]
        listed = ask.split('for example: ', 1)[1].rsplit('. Which', 1)[0].split('; ') if 'for example: ' in ask else []
        emitted += listed
        w2 &= all(t in allowed for t in emitted)
        if a2['action'] == 'fail_closed' or listed:
            w3 &= len(ask.split()) <= 70 and 1 <= len(listed) <= 3
        text = ' '.join(c['text'].split(': ', 1)[0] for c in o2['claims'] if c['text'].startswith('Only if')) + ' ' + ask
        for t in emitted:
            text = text.replace(t, '')
        w5 &= not re.search(r'\b4\d{3}\b', text)
        shown[name] = {'prefixes': [c['text'].split(': ', 1)[0] for c in o2['claims'] if c['text'].startswith('Only if')], 'ask': ask}
    verdict = {'W1': w1, 'W2': w2, 'W3': w3, 'W4': w4, 'W5': w5}
    verdict['overall_pass'] = all(verdict.values())
    return {'shown': shown, 'verdict': verdict}


def main_v2():
    text = PROTOCOL2.read_text()
    result = evaluate_v2(json.loads(BUNDLE.read_text())['cases'])
    result['protocol_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    (PROTOCOL2.parent / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


def main():
    import sys
    if '--version' in sys.argv:
        v = sys.argv[sys.argv.index('--version') + 1]
        return {'2': main_v2, '3': main_v3, '4': main_v4}[v]()
    text = PROTOCOL.read_text()
    result = evaluate(json.loads(BUNDLE.read_text())['cases'])
    result['protocol_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    (PROTOCOL.parent / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
