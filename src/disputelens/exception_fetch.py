"""Advisory parent-section fetch for ambiguous exceptions (v1). Offline; stdlib only.

Rule and thresholds are fixed in eval/experiments/exception-fetch-v1/protocol.json.
"""
import hashlib
import json
import re
from pathlib import Path

from .exception_referent import BUNDLE
from .exception_resolver import SPLIT, exception_tokens, requirement_stem, run

PROTOCOL = Path('eval/experiments/exception-fetch-v1/protocol.json')
CHUNKS = Path('data/chunks-expanded/chunks-400-overlap-40.json')
PARENT = 'mastercard-chargeback-guide'
GENERIC = {'issuer', 'chargeback', 'submission', 'case', 'dispute', 'message', 'reason', 'code'}
WORD = re.compile(r'[a-z][a-z-]{3,}')
MAX_WINDOW_WORDS = 120
MAX_CANDIDATES = 3


def heading_words(headings):
    text = ' '.join(headings[2:]).lower()
    return {w for w in WORD.findall(text) if w not in GENERIC}


def find_candidates(passage_headings, tokens, chunks):
    wanted = heading_words(passage_headings)
    found = []
    for chunk in chunks:
        sentences = [x.strip() for x in SPLIT.split(' '.join(chunk['text'].split())) if x.strip()]
        for i, sentence in enumerate(sentences):
            if requirement_stem(sentence) and any(t in sentence.lower() for t in tokens):
                window = sentences[max(0, i - 1):i + 2]
                found.append({'chunk_id': chunk['chunk_id'], 'stem': requirement_stem(sentence),
                              'headings': chunk['headings'][2:], 'sentence': sentence,
                              'window_words': len(' '.join(window).split()),
                              'shared': len(wanted & heading_words(chunk['headings'])), 'chunk_words': len(chunk['text'].split())})
    found.sort(key=lambda c: (-c['shared'], c['chunk_words']))
    seen, unique = set(), []
    for c in found:
        key = (c['chunk_id'], c['sentence'])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique[:MAX_CANDIDATES]


def evaluate(cases, chunks, protocol):
    resolved = run(cases, version=2)
    index = {}
    for case in cases:
        used = case['frozen_context_pack']['budget']['used']
        for group in case['frozen_context_pack']['groups']:
            for ev in group['evidence']:
                index[f"{case['case_id']}:{ev['citation_id']}"] = (ev, 6000 - used)
    plan = protocol['passages']
    report = {}
    for key, outcome in resolved.items():
        if outcome['outcome'] == 'resolved':
            continue
        ev, headroom = index[key]
        tokens = exception_tokens(ev['text'])
        if not tokens:
            report[key] = {'result': 'not applicable', 'searched': False}
            continue
        candidates = find_candidates(ev['headings'], tokens, chunks)
        report[key] = {'result': 'candidates' if candidates else 'none found', 'searched': True,
                       'context_headroom_words': headroom, 'candidates': candidates}
    t1 = all(report[k]['candidates'] and 'no cardholder authorization' in ' '.join(report[k]['candidates'][0]['headings']).lower()
             and report[k]['candidates'][0]['stem'] == 'list' for k in plan['section_has_answer_elsewhere'])
    t2 = all(len(r.get('candidates', [])) <= MAX_CANDIDATES and all(c['window_words'] <= MAX_WINDOW_WORDS for c in r.get('candidates', []))
             for r in report.values())
    t3 = all(report[k]['result'] == 'not applicable' and not report[k]['searched'] for k in plan['not_applicable'])
    t4 = all(k in report and report[k]['result'] in ('candidates', 'none found') for k in plan['other_applicable'])
    return {'report': report, 'verdict': {'T1': t1, 'T2': t2, 'T3': t3, 'T4': t4, 'overall_pass': t1 and t2 and t3 and t4}}


def main():
    protocol_text = PROTOCOL.read_text()
    protocol = json.loads(protocol_text)
    chunks = [c for c in json.loads(CHUNKS.read_text())['chunks'] if c['parent_id'] == PARENT]
    result = evaluate(json.loads(BUNDLE.read_text())['cases'], chunks, protocol)
    result['protocol_sha256'] = hashlib.sha256(protocol_text.encode()).hexdigest()
    (PROTOCOL.parent / 'result.json').write_text(json.dumps(result, indent=2))
    for key, value in result['report'].items():
        top = value.get('candidates', [None])[0] if value.get('candidates') else None
        print(key, value['result'], '| headroom', value.get('context_headroom_words'),
              '| top:', (' > '.join(top['headings'])[:80] + ' | ' + str(top['window_words']) + 'w') if top else '-')
    print(result['verdict'])


if __name__ == '__main__':
    main()
