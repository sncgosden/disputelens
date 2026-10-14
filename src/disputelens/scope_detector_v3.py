"""Scope detector v3: v2 plus subtype-by-description. Offline; stdlib only.

Rule and thresholds are fixed in eval/experiments/scope-detector-v3/protocol.json.
Separate module so the frozen scope_detector.py is untouched.
"""
import hashlib
import json
import re
from pathlib import Path

from .scope_detector import BUNDLE, PHRASES, unestablished

PROTOCOL = Path('eval/experiments/scope-detector-v3/protocol.json')
STRESS = Path('eval/stress/mastercard-scope-v1/pairs.json')
STOP = {'the', 'and', 'for', 'was', 'were', 'either', 'not', 'from', 'with', 'within', 'that', 'this', 'any', 'all'}
GENERIC = {'goods', 'services', 'charge', 'chargeback', 'dispute', 'transaction', 'issuer', 'acquirer',
           'merchant', 'cardholder', 'purchase', 'amount', 'case'}
SHARE = 0.5


def stem(word):
    if len(word) > 4:
        for suffix in ('ing', 'ed', 'es', 's'):
            if word.endswith(suffix):
                return word[:-len(suffix)]
    return word


def words(text):
    return {stem(w) for w in re.findall(r'[a-z]+', text.lower()) if len(w) >= 3}


def heading_words(heading):
    cleaned = re.sub(r'\([^)]*\)', ' ', heading)
    return {stem(w) for w in re.findall(r'[a-z]+', cleaned.lower())
            if len(w) >= 3 and w not in STOP and stem(w) not in {stem(g) for g in GENERIC}}


def subtype_established(headings, question):
    if len(headings) < 4:
        return False
    wanted = heading_words(' '.join(headings[3].split()))
    if not wanted:
        return False
    hit = wanted & words(question)
    return bool(hit) and len(hit) / len(wanted) >= SHARE


def unestablished_v3(headings, question):
    flagged = unestablished(headings, question, 2)
    if flagged and subtype_established(headings, question):
        return [x for x in flagged if x in PHRASES]
    return flagged


def evaluate(cases, rows):
    scoped = [r for r in rows if r['label'] == 'scoped']
    unscoped = [r for r in rows if r['label'] == 'unscoped']
    flag = lambda fn, r: bool(fn(r['cited_headings'], r['question']))
    v2 = lambda h, q: unestablished(h, q, 2)
    per_row = {r['id']: {'label': r['label'], 'v2': flag(v2, r), 'v3': flag(unestablished_v3, r)} for r in rows}
    t1 = sum(per_row[r['id']]['v3'] for r in unscoped) >= 11
    v3_false = sum(per_row[r['id']]['v3'] for r in scoped)
    v2_false = sum(per_row[r['id']]['v2'] for r in scoped)
    t2, t3 = v3_false <= 2, v3_false < v2_false
    same, flagged_cases = True, {}
    for case in cases:
        if case['saved_status'] != 'citation_valid_requires_review':
            continue
        index = {e['citation_id']: e for g in case['frozen_context_pack']['groups'] for e in g['evidence']}
        cited = {c['id'] for cl in case['answer']['claims'] for c in cl['citations'] if c['id'] in index}
        a = {i for i in cited if unestablished(index[i]['headings'], case['question'], 2)}
        b = {i for i in cited if unestablished_v3(index[i]['headings'], case['question'])}
        if a != b:
            same = False
        if b:
            flagged_cases[case['case_id']] = sorted(b)
    verdict = {'T1': t1, 'T2': t2, 'T3': t3, 'T4': same and set(flagged_cases) == {'E13', 'E22'}}
    return {'per_row': per_row, 'unscoped_flagged_v3': sum(per_row[r['id']]['v3'] for r in unscoped),
            'unscoped_flagged_v2': sum(per_row[r['id']]['v2'] for r in unscoped),
            'scoped_false_flags_v2': v2_false, 'scoped_false_flags_v3': v3_false,
            'dev_flagged_cases_v3': flagged_cases, 'verdict': verdict}


def main():
    result = evaluate(json.loads(BUNDLE.read_text())['cases'], json.loads(STRESS.read_text())['rows'])
    result['verdict']['overall_pass_excluding_T5'] = all(result['verdict'].values())
    result['protocol_sha256'] = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    result['stress_sha256'] = hashlib.sha256(STRESS.read_bytes()).hexdigest()
    (PROTOCOL.parent / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))




# --- near-miss evaluation and operating-point sweep (scope-detector-v3-nearmiss protocol) ---
NEARMISS = Path('eval/stress/mastercard-scope-v1/nearmiss.json')
PROTOCOL_NM = Path('eval/experiments/scope-detector-v3-nearmiss/protocol.json')


def established(headings, question, share, min_hits):
    if len(headings) < 4:
        return False
    wanted = heading_words(' '.join(headings[3].split()))
    hit = wanted & words(question)
    return bool(wanted) and len(hit) >= min_hits and len(hit) / len(wanted) >= share


def flagged_at(headings, question, share, min_hits):
    flagged = unestablished(headings, question, 2)
    if flagged and established(headings, question, share, min_hits):
        return [x for x in flagged if x in PHRASES]
    return flagged


def evaluate_nearmiss(cases):
    pairs = json.loads(STRESS.read_text())['rows']
    near = json.loads(NEARMISS.read_text())['rows']
    scoped = [r for r in pairs if r['label'] == 'scoped']
    unscoped = [r for r in pairs if r['label'] == 'unscoped']
    count = lambda rows, fn: sum(bool(fn(r['cited_headings'], r['question'])) for r in rows)
    v2 = lambda h, q: unestablished(h, q, 2)
    v3 = unestablished_v3
    per_row = {r['id']: {'v2': bool(v2(r['cited_headings'], r['question'])), 'v3': bool(v3(r['cited_headings'], r['question']))} for r in near}
    n1 = count(near, v3) >= len(near) - 3
    n2 = count(near, v2) == len(near)
    sweep = []
    for share in (0.34, 0.5, 0.67, 1.0):
        for hits in (1, 2):
            fn = lambda h, q, s=share, m=hits: flagged_at(h, q, s, m)
            sweep.append({'share': share, 'min_hits': hits, 'scoped_false_flags_of_12': count(scoped, fn),
                          'unscoped_flagged_of_12': count(unscoped, fn), 'nearmiss_cleared_of_12': len(near) - count(near, fn)})
    return {'per_row': per_row, 'nearmiss_cleared_v3': len(near) - count(near, v3), 'nearmiss_cleared_v2': len(near) - count(near, v2),
            'sweep': sweep, 'verdict': {'N1': n1, 'N2': n2, 'overall_pass': n1 and n2}}


def main_nearmiss():
    result = evaluate_nearmiss(json.loads(BUNDLE.read_text())['cases'])
    result['protocol_sha256'] = hashlib.sha256(PROTOCOL_NM.read_bytes()).hexdigest()
    (PROTOCOL_NM.parent / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    import sys
    main_nearmiss() if '--nearmiss' in sys.argv else main()
