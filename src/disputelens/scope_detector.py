"""Advisory scope-qualifier detector (v1). Offline; never authorises or excludes evidence.

Flags cited passages whose heading path carries a specialised scope (reason code or named
subtype) that the question text never established. Rule and thresholds are fixed in
eval/experiments/scope-detector-v1/protocol.json.
"""
import glob
import hashlib
import json
import re
from pathlib import Path

PROTOCOL = Path('eval/experiments/scope-detector-v1/protocol.json')
BUNDLE = Path('data/indexes/answer-eval-plan/c36f49c3b45e0291a3d40299/independent-review-bundle.json')
REVIEW_GLOB = 'data/indexes/answer-eval-plan/c36f49c3b45e0291a3d40299/manual-review-batch-0*.json'
PHRASES = ('participating countries', 'stand-in', 'x-code', 'required authorization')
CODE = re.compile(r'(?<!\d)(4\d{3})(?!\d)')


def qualifiers(headings):
    """Codes from the deepest heading below chapter level that has any, plus named subtype phrases."""
    below_chapter = list(headings[2:])
    codes = set()
    for heading in reversed(below_chapter):
        found = set(CODE.findall(heading))
        if found:
            codes = found
            break
    text = ' '.join(below_chapter).lower()
    return codes, {p for p in PHRASES if p in text}


def named_in_question(headings, question):
    """v2 R2: the question names a section heading in words (two or more words, parenthetical removed)."""
    lowered = ' '.join(question.lower().split())
    for heading in headings[2:]:
        name = ' '.join(re.sub(r'\([^)]*\)', '', heading).lower().split())
        if len(name.split()) >= 2 and name in lowered:
            return True
    return False


def unestablished(headings, question, version=1):
    codes, phrases = qualifiers(headings)
    asked = set(CODE.findall(question))
    lowered = question.lower()
    if version >= 2:
        if named_in_question(headings, question):
            return []
        if codes & asked:
            codes = set()
    return sorted(codes - asked) + sorted(p for p in phrases if p not in lowered)


def flag_case(case, version=1):
    index = {e['citation_id']: e for g in case['frozen_context_pack']['groups'] for e in g['evidence']}
    flagged = {}
    for claim in case['answer'].get('claims', []):
        for cite in claim.get('citations', []):
            evidence = index.get(cite['id'])
            if evidence:
                missing = unestablished(evidence['headings'], case['question'], version)
                if missing:
                    flagged[cite['id']] = missing
    return flagged


def applicability_ratings(pattern=REVIEW_GLOB):
    ratings = {}
    for path in sorted(glob.glob(pattern)):
        for item in json.loads(Path(path).read_text()).get('cases', []):
            ratings[item['case_id']] = (item.get('ratings') or {}).get('faithfulness_applicability')
    return ratings


def evaluate(cases, ratings, protocol, version=1, max_false=3):
    results = {c['case_id']: flag_case(c, version) for c in cases if c['saved_status'] == 'citation_valid_requires_review'}
    known = protocol['known_defective_passages']
    hit = sum(1 for case_id, ids in known.items() for i in ids if i in results.get(case_id, {}))
    total = sum(len(ids) for ids in known.values())
    control_flags = {c: sorted(results.get(c, {})) for c in protocol['controls'] if results.get(c)}
    clean = [c for c, r in ratings.items() if r == 2]
    false_flagged = sorted(c for c in clean if results.get(c))
    verdict = {
        'T1_known_defect_recall': {'value': f'{hit}/{total}', 'pass': hit == total},
        'T2_control_false_flags': {'value': control_flags or 'none', 'pass': not control_flags},
        'T3_false_flag_rate': {'value': f'{len(false_flagged)}/{len(clean)}', 'cases': false_flagged, 'pass': len(false_flagged) <= max_false},
    }
    return {'flags': {c: r for c, r in results.items() if r}, 'verdict': verdict,
            'overall_pass': all(v['pass'] for v in verdict.values())}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    protocol_path = Path(f'eval/experiments/scope-detector-v{args.version}/protocol.json')
    protocol_text = protocol_path.read_text()
    protocol = json.loads(protocol_text)
    protocol.setdefault('known_defective_passages', json.loads(PROTOCOL.read_text())['known_defective_passages'])
    protocol.setdefault('controls', json.loads(PROTOCOL.read_text())['controls'])
    cases = json.loads(BUNDLE.read_text())['cases']
    ratings = applicability_ratings()
    report = evaluate(cases, ratings, protocol, args.version, 3 if args.version == 1 else 1)
    if args.version == 2:
        v1 = evaluate(cases, ratings, protocol, 1)['flags']
        extra = {c: sorted(set(ids) - set(v1.get(c, {}))) for c, ids in report['flags'].items()}
        extra = {c: i for c, i in extra.items() if i}
        report['verdict']['T4_monotone'] = {'value': extra or 'subset of v1', 'pass': not extra}
        report['overall_pass'] = all(v['pass'] for v in report['verdict'].values())
        report['removed_vs_v1'] = {c: sorted(set(ids) - set(report['flags'].get(c, {}))) for c, ids in v1.items()
                                   if set(ids) - set(report['flags'].get(c, {}))}
    report['protocol_sha256'] = hashlib.sha256(protocol_text.encode()).hexdigest()
    out = protocol_path.parent / 'result.json'
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in report if k in ('verdict', 'overall_pass', 'removed_vs_v1')}, indent=2))
    print('flagged cases:', ', '.join(sorted(report['flags'])) or 'none')
    print('Saved ' + str(out) + '. Offline; no model calls; holdout untouched.')


if __name__ == '__main__':
    main()
