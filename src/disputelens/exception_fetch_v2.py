"""Advisory section-hierarchy fetch for ambiguous exceptions (v2). Offline; stdlib only.

Rule and thresholds are fixed in eval/experiments/exception-fetch-v2/protocol.json.
"""
import hashlib
import json
from pathlib import Path

from .exception_referent import BUNDLE
from .exception_resolver import SPLIT, exception_tokens, requirement_stem, run

PROTOCOL = Path('eval/experiments/exception-fetch-v2/protocol.json')
CHUNKS = Path('data/indexes/section-hierarchy/71bf6051f48778a5e9ca12c1/chunks.json')
PARENT = 'mastercard-chargeback-guide'
MAX_WORDS = 60
MAX_CANDIDATES = 3
RESERVE = 100
CAP = 6000
SECTION = 'message reason code'
LABEL_NOTE = 'possibly related, scope not confirmed'


def clean(headings):
    return [' '.join(h.split()) for h in headings[2:]]


def shared_depth(a, b):
    n = 0
    for x, y in zip(clean(a), clean(b)):
        if x != y:
            break
        n += 1
    return n


def relatedness(passage_headings, chunk_headings):
    a, b = clean(passage_headings), clean(chunk_headings)
    if a == b:
        return 'same step'
    depth = shared_depth(passage_headings, chunk_headings)
    if any(SECTION in h.lower() for h in a[:depth]) and depth >= 3:
        return 'same section, different step'
    return 'unrelated'


def find_candidates(passage_headings, tokens, chunks):
    found = []
    for chunk in chunks:
        sentences = [x.strip() for x in SPLIT.split(' '.join(chunk['text'].split())) if x.strip()]
        for sentence in sentences:
            if requirement_stem(sentence) and any(t in sentence.lower() for t in tokens):
                found.append({'chunk_id': chunk['chunk_id'], 'stem': requirement_stem(sentence),
                              'headings': clean(chunk['headings']), 'sentence': sentence,
                              'words': len(sentence.split()),
                              'depth': shared_depth(passage_headings, chunk['headings']),
                              'relatedness': relatedness(passage_headings, chunk['headings']),
                              'status': LABEL_NOTE, 'chunk_words': len(chunk['text'].split())})
    found.sort(key=lambda c: (-c['depth'], c['chunk_words']))
    seen, unique = set(), []
    for c in found:
        key = (c['chunk_id'], c['sentence'])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique[:MAX_CANDIDATES]


def eviction(case, sentence_words):
    pack = case['frozen_context_pack']
    headroom = CAP - pack['budget']['used']
    need = max(0, max(RESERVE, sentence_words) - headroom)
    cited = {c['id'] for claim in case['answer'].get('claims', []) for c in claim.get('citations', [])}
    free = sorted(((len(ev['text'].split()), ev['citation_id']) for g in pack['groups'] for ev in g['evidence']
                   if ev['citation_id'] not in cited), reverse=True)
    evicted, freed = [], 0
    for words, cid in free:
        if freed >= need:
            break
        evicted.append(cid)
        freed += words
    return {'headroom': headroom, 'words_to_evict': need, 'evicted': evicted,
            'cited_evicted': 0, 'feasible': freed >= need}


def evaluate(cases, chunks, protocol):
    resolved = run(cases, version=2)
    by_case = {c['case_id']: c for c in cases}
    index = {}
    for case in cases:
        for group in case['frozen_context_pack']['groups']:
            for ev in group['evidence']:
                index[f"{case['case_id']}:{ev['citation_id']}"] = ev
    plan = protocol['passages']
    report = {}
    for key, outcome in resolved.items():
        if outcome['outcome'] == 'resolved':
            continue
        ev = index[key]
        tokens = exception_tokens(ev['text'])
        if not tokens:
            report[key] = {'result': 'not applicable', 'searched': False}
            continue
        cands = find_candidates(ev['headings'], tokens, chunks)
        report[key] = {'result': 'candidates' if cands else 'none found', 'searched': True, 'candidates': cands}
    costs = {}
    for cid in ('E13', 'E23', 'E15'):
        words = max([c['words'] for k, r in report.items() if k.startswith(cid + ':') for c in r.get('candidates', [])] or [0])
        costs[cid] = dict(eviction(by_case[cid], words), sentence_words=words)
    keys = plan['section_has_answer_elsewhere']
    t1 = (all(report[k]['candidates'] and all(c['depth'] >= 1 for c in report[k]['candidates']) for k in keys + plan['other_applicable']
              if report[k]['candidates'])
          and all(report[k]['candidates'] and report[k]['candidates'][0]['stem'] == 'list' for k in keys))
    t2 = all(len(r.get('candidates', [])) <= MAX_CANDIDATES and all(c['words'] <= MAX_WORDS for c in r.get('candidates', []))
             for r in report.values())
    t3 = all(report[k]['result'] == 'not applicable' and not report[k]['searched'] for k in plan['not_applicable'])
    t4 = all(k in report and report[k]['result'] in ('candidates', 'none found') for k in plan['other_applicable'])
    t5 = all(c['status'] == LABEL_NOTE and c['relatedness'] for r in report.values() for c in r.get('candidates', []))
    t6 = all(c['feasible'] and c['cited_evicted'] == 0 for c in costs.values())
    v = {'T1': t1, 'T2': t2, 'T3': t3, 'T4': t4, 'T5': t5, 'T6': t6}
    v['overall_pass'] = all(v.values())
    return {'report': report, 'costs': costs, 'verdict': v}


def main():
    protocol_text = PROTOCOL.read_text()
    protocol = json.loads(protocol_text)
    chunks = [c for c in json.loads(CHUNKS.read_text())['chunks'] if c['parent_id'] == PARENT]
    result = evaluate(json.loads(BUNDLE.read_text())['cases'], chunks, protocol)
    result['protocol_sha256'] = hashlib.sha256(protocol_text.encode()).hexdigest()
    (PROTOCOL.parent / 'result.json').write_text(json.dumps(result, indent=2))
    for key, value in result['report'].items():
        top = value['candidates'][0] if value.get('candidates') else None
        print(key, value['result'], '|', (f"{top['relatedness']} depth {top['depth']} {top['words']}w {top['chunk_id'][-8:]}" if top else '-'))
    print(json.dumps(result['costs']))
    print(result['verdict'])


if __name__ == '__main__':
    main()
