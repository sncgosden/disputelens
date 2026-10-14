"""Advisory resolver: bind a vague exception to a listed requirement using sibling evidence (v1). Offline.

Rule and thresholds are fixed in eval/experiments/exception-resolver-v1/protocol.json.
"""
import hashlib
import json
import re
from pathlib import Path

from .exception_referent import BUNDLE, EXCEPTION, vague_exception

PROTOCOL = Path('eval/experiments/exception-resolver-v1/protocol.json')
REQUIREMENT = re.compile(r'^[\W_]*(listing|closing|blocking)\b.*\brequired\b', re.I)
GERUND = {'listing': 'list', 'closing': 'close', 'blocking': 'block'}
TOKENS = ('mainland china', 'latin america and the caribbean', 'germany', 'cat 2')
STEMS = {'close': re.compile(r'\bclos'), 'block': re.compile(r'\bblock'), 'list': re.compile(r'\blist|stand-in')}
SPLIT = re.compile(r'(?<=[.;])\s+|\n\s*[–•-]\s+')


def exception_tokens(text):
    match = EXCEPTION.search(text)
    tail = ' '.join(text[match.start():match.start() + 700].lower().split()) if match else ''
    return [t for t in TOKENS if t in tail]


def stems_in(sentence):
    return [name for name, pattern in STEMS.items() if pattern.search(sentence)]


def requirement_stem(sentence):
    """v2: stem named by a requirement statement such as 'Listing the PAN ... is required', else None."""
    match = REQUIREMENT.match(sentence.strip())
    return GERUND[match.group(1).lower()] if match else None


def resolve(passage, siblings, version=1):
    """Return {'outcome': resolved|conflicting|ambiguous, 'stem': ..., 'by': [passage ids]}."""
    tokens = exception_tokens(passage['text'])
    if not tokens:
        return {'outcome': 'ambiguous', 'reason': 'no distinctive exception tokens'}
    found = {}
    for other in siblings:
        if other['citation_id'] == passage['citation_id']:
            continue
        for sentence in SPLIT.split(' '.join(other['text'].split())):
            low = sentence.lower()
            if version >= 2:
                stem = requirement_stem(sentence)
                hit = [stem] if stem else []
            else:
                hit = stems_in(low)
            if len(hit) == 1 and any(t in low for t in tokens):
                found.setdefault(hit[0], set()).add(other['citation_id'])
    if not found:
        return {'outcome': 'ambiguous', 'reason': 'no sibling sentence names a requirement'}
    if len(found) > 1:
        return {'outcome': 'conflicting', 'stems': sorted(found)}
    stem, ids = next(iter(found.items()))
    return {'outcome': 'resolved', 'stem': stem, 'by': sorted(ids)}


def run(cases, version=1):
    results = {}
    for case in cases:
        for group in case['frozen_context_pack']['groups']:
            for evidence in group['evidence']:
                if vague_exception(evidence['text']):
                    results[f"{case['case_id']}:{evidence['citation_id']}"] = resolve(evidence, group['evidence'], version)
    return results


def verdict(results, version=1):
    e23 = {k: v for k, v in results.items() if k.startswith('E23:')}
    t1 = results.get('E23:S045', {}).get('outcome') == 'resolved' and results['E23:S045'].get('stem') == 'list'
    t4 = not any(v.get('stem') in ('close', 'block') for v in e23.values())
    t5 = all(v.get('outcome') in ('resolved', 'conflicting', 'ambiguous') for v in results.values())
    out = {'T1_E23_S045_resolves_to_list': t1, 'T2_no_close_or_block_in_E23': t4, 'T3_every_flag_has_one_outcome': t5}
    if version >= 2:
        r = results.get('E15:S085', {})
        out = {'T1_E23_S045_resolves_to_list_by_S044': t1 and results['E23:S045'].get('by') == ['S044'],
               'T2_E15_S085_resolves_to_list_by_S084': r.get('outcome') == 'resolved' and r.get('stem') == 'list' and r.get('by') == ['S084'],
               'T3_E13_S030_and_S034_ambiguous': all(results.get(k, {}).get('outcome') == 'ambiguous' for k in ('E13:S030', 'E13:S034')),
               'T4_no_close_or_block_in_E23': t4, 'T5_every_flag_has_one_outcome': t5 and len(results) == 12}
    out['overall_pass'] = all(out.values())
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    protocol_path = Path(f'eval/experiments/exception-resolver-v{args.version}/protocol.json')
    protocol_text = protocol_path.read_text()
    results = run(json.loads(BUNDLE.read_text())['cases'], args.version)
    report = {'results': results, 'verdict': verdict(results, args.version),
              'protocol_sha256': hashlib.sha256(protocol_text.encode()).hexdigest()}
    (protocol_path.parent / 'result.json').write_text(json.dumps(report, indent=2))
    for key, value in results.items():
        print(key, value)
    print(report['verdict'])


if __name__ == '__main__':
    main()
