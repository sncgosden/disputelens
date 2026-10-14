"""Prepare and score the flagged-answer regeneration test. Offline; no model call here.

Rule, criteria and budget are fixed in eval/experiments/flagged-answer-v1/protocol.json.
"""
import hashlib
import json
import re
from pathlib import Path

from .grounded_answer import SYSTEM, build_answer_prompt
from .scope_detector import BUNDLE, flag_case, unestablished

PROTOCOL = Path('eval/experiments/flagged-answer-v1/protocol.json')
OUT = Path('data/indexes/flagged-answer-trial')
CASES = ('E13', 'E22')
MODEL = 'claude-sonnet-5-5'
MARKER = re.compile(r"\b(only if|only when|applies only|if your|if you|if the)\b", re.I)
ADDENDUM = """
SCOPE NOTICE. The user JSON includes scope_not_established: source IDs whose section applies
only within a qualifier the question has not established (a reason code, a named program such
as participating countries, or a stand-in/authorization subtype). Rules for those sources:
1. Never state their procedures as instructions to the merchant.
2. Keep established sources as ordinary claims.
3. A flagged source may appear only as a conditional claim that begins with "Only if" and names
   the unestablished qualifier, still with its citation and exact quote.
4. Put the single missing scope fact into missing_information. If no established source answers the
   question, return status needs_clarification with no unconditional claims and ask for that fact."""


def system_text():
    return SYSTEM + '\n' + ADDENDUM


def build_request(case):
    pack = case['frozen_context_pack']
    flagged = flag_case(case, 2)
    body = json.loads(build_answer_prompt(case['question'], pack))
    body['scope_not_established'] = flagged
    return flagged, {'model': MODEL, 'max_tokens': 8192, 'system': system_text(),
                     'messages': [{'role': 'user', 'content': json.dumps(body, ensure_ascii=False)}]}


def controls_unflagged(cases):
    return {c['case_id']: flag_case(c, 2) for c in cases if c['case_id'] not in CASES
            and c['saved_status'] == 'citation_valid_requires_review' and flag_case(c, 2)}


def score(case, answer):
    """Mechanical M2-M4 on a validated second answer; M5 is a source review."""
    index = {e['citation_id']: e for g in case['frozen_context_pack']['groups'] for e in g['evidence']}
    flagged_ids = {i for i, e in index.items() if unestablished(e['headings'], case['question'], 2)}
    unconditional_flagged, unconditional_established = [], 0
    for n, claim in enumerate(answer.get('claims', []), 1):
        ids = {c['id'] for c in claim['citations']}
        if ids & flagged_ids:
            if not MARKER.search(claim['text']):
                unconditional_flagged.append(n)
        elif MARKER.search(claim['text']) is None:
            unconditional_established += 1
    missing = ' '.join(answer.get('missing_information', [])).lower()
    m3 = answer['status'] in ('needs_clarification', 'partial') and ('reason code' in missing or 'dispute type' in missing)
    return {'M2': not unconditional_flagged, 'unconditional_flagged_claims': unconditional_flagged,
            'M3': m3 if case['case_id'] == 'E22' else None,
            'M4': unconditional_established >= 1 if case['case_id'] == 'E13' else None}


def prepare():
    protocol_text = PROTOCOL.read_text()
    cases = json.loads(BUNDLE.read_text())['cases']
    stray = controls_unflagged(cases)
    if stray:
        raise SystemExit(f'Controls unexpectedly flagged: {stray}')
    out = OUT / hashlib.sha256(protocol_text.encode()).hexdigest()[:24]
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for case in cases:
        if case['case_id'] in CASES:
            flagged, body = build_request(case)
            prompt_sha = hashlib.sha256((body['system'] + '\n' + body['messages'][0]['content']).encode()).hexdigest()
            (out / f"{case['case_id']}-request.json").write_text(json.dumps(body, indent=2, ensure_ascii=False))
            summary[case['case_id']] = {'flagged': flagged, 'prompt_sha256': prompt_sha,
                                       'user_words': len(body['messages'][0]['content'].split()) + len(body['system'].split())}
    (out / 'prepared.json').write_text(json.dumps({'protocol_sha256': hashlib.sha256(protocol_text.encode()).hexdigest(),
                                                  'cases': summary}, indent=2))
    print(out)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    prepare()
