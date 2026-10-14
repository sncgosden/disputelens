"""Tolerant quote check experiment (offline). validate_answer itself is NOT changed.

Rule and thresholds are fixed in eval/experiments/quote-match-v1/protocol.json.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

from .client import ModelError
from .grounded_answer import validate_answer
from .scope_detector import BUNDLE

PROTOCOL = Path('eval/experiments/quote-match-v1/protocol.json')
FLAGGED_ATTEMPT = Path('data/indexes/flagged-answer-trial/634d43ae4d6ad7e164c1c684/E13-claude-attempt.json')
HYPHEN_GAP = re.compile(r'(?<=-)\s+')
MISMATCH = 'does not match cited source wording'


def strip_gaps(text):
    return HYPHEN_GAP.sub('', ' '.join(text.split()))


def validate_tolerant(text, pack):
    """Strict validation first; only a pure wording-mismatch is retried with hyphen gaps removed on both sides."""
    try:
        return validate_answer(text, pack), False
    except ModelError as error:
        if MISMATCH not in str(error):
            raise
    data = json.loads(text)
    for claim in data.get('claims', []):
        for citation in claim.get('citations', []):
            if isinstance(citation.get('quote'), str):
                citation['quote'] = strip_gaps(citation['quote'])
    shadow = copy.deepcopy(pack)
    for group in shadow['groups']:
        for evidence in group['evidence']:
            evidence['text'] = strip_gaps(evidence['text'])
    return validate_answer(json.dumps(data), shadow), True


def passages(case):
    return {e['citation_id']: e['text'] for g in case['frozen_context_pack']['groups'] for e in g['evidence']}


def negative_controls(case):
    """Six mutations of a real quote that must still fail."""
    for cid, text in passages(case).items():
        flat = ' '.join(text.split())
        words = flat.split()
        if len(words) < 60:
            continue
        base = ' '.join(words[10:24])
        number = re.search(r'\d+', base)
        if not number or ' not ' in base or '-' not in flat:
            continue
        hy = re.search(r'\S*-\S*', flat)
        if not hy:
            continue
        i = flat.find(hy.group(0))
        quote_hy = flat[max(0, i - 30):i + 30]
        stitched = ' '.join(words[0:6]) + ' ' + ' '.join(words[30:36])
        return cid, {
            'changed_word': base.replace(words[12], 'zzzzword', 1),
            'changed_number': base[:number.start()] + str(int(number.group()) + 7) + base[number.end():],
            'removed_not': ' '.join(words[10:14]) + ' not ' + ' '.join(words[14:24]),
            'stitched_a': stitched,
            'stitched_b': ' '.join(words[40:44]) + ' ' + ' '.join(words[2:6]),
            'altered_letter_near_hyphen': quote_hy.replace(hy.group(0), hy.group(0)[:-1] + 'x', 1),
        }
    return None, {}


def one_answer(quote_id, quote):
    return json.dumps({'status': 'partial', 'claims': [{'text': 'c', 'citations': [{'id': quote_id, 'quote': quote}]}],
                       'missing_information': ['m']})


def evaluate(cases):
    source = Path('src/disputelens/grounded_answer.py')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    by_id = {c['case_id']: c for c in cases}
    attempt = json.loads(FLAGGED_ATTEMPT.read_text())
    try:
        _, used = validate_tolerant(attempt['raw_response'], by_id['E13']['frozen_context_pack'])
        h1 = True
    except ModelError:
        h1, used = False, False
    h2, differing = True, []
    for case in cases:
        if case['saved_status'] != 'citation_valid_requires_review':
            continue
        text = json.dumps(case['answer'])
        strict = validate_answer(text, case['frozen_context_pack'])
        tolerant, changed = validate_tolerant(text, case['frozen_context_pack'])
        if changed or strict['citation_checks'] != tolerant['citation_checks']:
            h2 = False
            differing.append(case['case_id'])
    h3 = {}
    for case in cases:
        if case['saved_status'] == 'citation_valid_requires_review':
            continue
        raw = json.loads(Path(case['attempt_path']).read_text()).get('raw_response', '')
        try:
            validate_tolerant(raw, case['frozen_context_pack'])
            h3[case['case_id']] = 'becomes valid'
        except ModelError as error:
            h3[case['case_id']] = 'still invalid: ' + str(error)[:70]
    rejected, controls = {}, []
    for case in cases:
        cid, mutated = negative_controls(case)
        if mutated:
            controls = [(case['case_id'], cid, mutated)]
            break
    if controls:
        case_id, cid, mutated = controls[0]
        for name, quote in mutated.items():
            try:
                validate_tolerant(one_answer(cid, quote), by_id[case_id]['frozen_context_pack'])
                rejected[name] = False
            except ModelError:
                rejected[name] = True
    h4 = len(rejected) == 6 and all(rejected.values())
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    verdict = {'H1': h1, 'H2': h2, 'H4': h4, 'H5': before == after}
    verdict['overall_pass'] = all(verdict.values())
    return {'e13_used_hyphen_rule': used, 'baseline_differing': differing, 'H3_failed_baseline': h3,
            'negative_controls': {'case': controls[0][0] if controls else None, 'rejected': rejected}, 'verdict': verdict}


def main():
    text = PROTOCOL.read_text()
    result = evaluate(json.loads(BUNDLE.read_text())['cases'])
    result['protocol_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    (PROTOCOL.parent / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
