"""Advisory detector: exception sentence with a vague referent after a list (v1). Offline; stdlib only.

Rule and thresholds are fixed in eval/experiments/exception-referent-v1/protocol.json.
"""
import glob
import hashlib
import json
import re
from pathlib import Path

PROTOCOL = Path('eval/experiments/exception-referent-v1/protocol.json')
BUNDLE = Path('data/indexes/answer-eval-plan/c36f49c3b45e0291a3d40299/independent-review-bundle.json')
REVIEW_GLOB = 'data/indexes/answer-eval-plan/c36f49c3b45e0291a3d40299/manual-review-batch-0*.json'
EXCEPTION = re.compile(r'\b(?:this|these|that|the above)\s+(?:requirements?|rules?|conditions?|steps?)\s+'
                       r'(?:(?:does|do)\s+not\s+apply|(?:is|are)\s+not\s+required)', re.I)
LIST_ITEM = re.compile(r'^\s*(?:[-–—•*]|\d+[.)])\s+\S')


def vague_exception(text):
    """Return the exception sentence if it follows at least two list items in the same passage."""
    match = EXCEPTION.search(text)
    if not match:
        return None
    before = text[:match.start()].splitlines()
    if sum(1 for line in before if LIST_ITEM.match(line)) < 2:
        return None
    end = text.find('.', match.end())
    return ' '.join(text[match.start():end if end != -1 else match.end() + 80].split())


def flag_case(case):
    index = {e['citation_id']: e for g in case['frozen_context_pack']['groups'] for e in g['evidence']}
    flagged = {}
    for claim in case['answer'].get('claims', []):
        for cite in claim.get('citations', []):
            evidence = index.get(cite['id'])
            sentence = vague_exception(evidence['text']) if evidence else None
            if sentence:
                flagged[cite['id']] = sentence
    return flagged


def correctness_ratings(pattern=REVIEW_GLOB):
    ratings = {}
    for path in sorted(glob.glob(pattern)):
        for item in json.loads(Path(path).read_text()).get('cases', []):
            ratings[item['case_id']] = (item.get('ratings') or {}).get('correctness')
    return ratings


def evaluate(cases, ratings, protocol):
    results = {c['case_id']: flag_case(c) for c in cases if c['saved_status'] == 'citation_valid_requires_review'}
    known = protocol['known_defective_passages']
    missed = [(c, i) for c, ids in known.items() for i in ids if i not in results.get(c, {})]
    control_flags = {c: sorted(results[c]) for c in protocol['controls'] if results.get(c)}
    clean = [c for c, r in ratings.items() if r == 2]
    false_flagged = sorted(c for c in clean if results.get(c))
    verdict = {
        'T1_known_defect': {'value': 'flagged' if not missed else f'missed {missed}', 'pass': not missed},
        'T2_control_false_flags': {'value': control_flags or 'none', 'pass': not control_flags},
        'T3_false_flag_rate': {'value': f'{len(false_flagged)}/{len(clean)}', 'cases': false_flagged, 'pass': len(false_flagged) <= 3},
    }
    return {'flags': {c: r for c, r in results.items() if r}, 'verdict': verdict,
            'overall_pass': all(v['pass'] for v in verdict.values())}


def main():
    protocol_text = PROTOCOL.read_text()
    protocol = json.loads(protocol_text)
    report = evaluate(json.loads(BUNDLE.read_text())['cases'], correctness_ratings(), protocol)
    report['protocol_sha256'] = hashlib.sha256(protocol_text.encode()).hexdigest()
    out = PROTOCOL.parent / 'result.json'
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('verdict', 'overall_pass', 'flags')}, indent=2))
    print('Saved ' + str(out) + '. Offline; no model calls; holdout untouched.')


if __name__ == '__main__':
    main()
