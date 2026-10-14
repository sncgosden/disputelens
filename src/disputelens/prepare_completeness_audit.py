"""Verify assisted clause dispositions and prepare an experimental prompt offline."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .client import ModelError
from .grounded_answer import SYSTEM, build_answer_prompt, validate_answer

CONFIG = Path('eval/experiments/completeness-v1/reviewed-clauses.json')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def draft_system():
    old = 'Answer only the aspects explicitly asked, using at most four concise claims.'
    if SYSTEM.count(old) != 1:
        raise ModelError('Baseline brevity instruction changed; review the experiment.')
    return SYSTEM.replace(old, '''Answer only the aspects explicitly asked. Use as many concise claims as necessary
to preserve every relevant supported requirement, alternative and qualification.
Before finalizing, check each requested aspect for omitted conditional duties.
Keep document alternatives distinct. State all mandatory details within each option.
An exception waives only the requirement it explicitly qualifies, not neighbouring
requirements. Retain its limiting conditions and any stated duration.
Distinguish missing merchant facts from missing evidence. If a conditional rule is
available but its applicability is unknown, state the rule conditionally and ask
for the missing fact. Do not describe available evidence as absent merely because
the merchant facts are unknown. Avoid unrelated branches and unasked advice.''')


def verify_review(config):
    """Check frozen provenance; semantic coverage is the named reviewer's input.

    This intentionally does not pretend to infer completeness from keyword matches.
    """
    if config.get('review_type') != 'Codex assisted clause review; not independent':
        raise ModelError('Expected explicit assisted review attribution.')
    if len(config['cases']) != 2 or {c['case_id'] for c in config['cases']} != {'E18', 'E23'}:
        raise ModelError('Only the two reviewed development cases are supported.')
    rows, packs = [], {}
    for case in config['cases']:
        for name in ('attempt', 'context_pack'):
            if digest(case[name + '_path']) != case[name + '_sha256']:
                raise ModelError('Reviewed input changed; do not carry ratings forward.')
        attempt = json.loads(Path(case['attempt_path']).read_text())
        pack = json.loads(Path(case['context_pack_path']).read_text())
        if (attempt['identity']['context_pack_sha256'] != case['context_pack_sha256']
                or attempt['question'] != pack['question']):
            raise ModelError('Attempt does not belong to reviewed context.')
        validate_answer(json.dumps(attempt['answer']), pack)
        packs[case['case_id']] = pack
        evidence = {e['citation_id']: e for g in pack['groups'] for e in g['evidence']}
        seen = set()
        for clause in case['clauses']:
            cid = clause['clause_id']
            if cid in seen or not cid or not clause['requirement'] or not clause['rationale']:
                raise ModelError('Clause IDs must be unique and dispositions explained.')
            seen.add(cid)
            if clause['coverage'] not in ('included', 'partial', 'omitted', 'acknowledged_source_gap'):
                raise ModelError('Unknown clause coverage disposition.')
            if clause['applicability'] not in ('question_general', 'conditional_facts_unknown', 'scope_unknown'):
                raise ModelError('Keep applicability separate from coverage.')
            nums = clause['answer_claim_numbers']
            if (len(nums) != len(set(nums)) or any(type(n) is not int or not 1 <= n <= len(attempt['answer']['claims']) for n in nums)
                    or (clause['coverage'] in ('included', 'partial') and not nums)
                    or (clause['coverage'] in ('omitted', 'acknowledged_source_gap') and nums)):
                raise ModelError('Invalid claim references for coverage disposition.')
            if not clause['citation_ids'] or any(label not in evidence for label in clause['citation_ids']):
                raise ModelError('Clause source is missing from the verified pack.')
            rows.append({'case_id': case['case_id'], **clause,
                'answer_excerpts': [attempt['answer']['claims'][n - 1]['text'] for n in nums],
                'source_evidence': [{'citation_id': label, 'passage_id': evidence[label]['passage_id'],
                    'locator': evidence[label]['locator'], 'headings': evidence[label]['headings'],
                    'text_sha256': hashlib.sha256(evidence[label]['text'].encode()).hexdigest()}
                    for label in clause['citation_ids']]})
    return rows, packs


def main():
    config = json.loads(CONFIG.read_text())
    rows, packs = verify_review(config)
    system = draft_system()
    identity = hashlib.sha256((digest(CONFIG) + digest(__file__) + SYSTEM + system).encode()).hexdigest()[:24]
    out = Path('data/indexes/completeness-audit') / identity
    if out.exists():
        print('Existing verified preparation preserved: ' + str(out))
        print('No model calls, retries or holdout access.')
        return 0
    out.mkdir(parents=True)
    counts = {cid: dict(Counter(r['coverage'] for r in rows if r['case_id'] == cid)) for cid in ('E18', 'E23')}
    report = {'identity': identity, 'reviewer': 'Codex', 'method': config['review_type'],
        'counts': counts, 'rows': rows, 'model_calls': 0,
        'limits': ['Review dispositions are source-backed assisted judgments, not automatic semantic scores.',
            'Conditional facts unknown do not excuse omission of available conditional requirements.',
            'Counts are checklist coverage, not aggregate accuracy.',
            'Draft removes claim cap AND adds completeness guidance; changes are not isolated.',
            'Four-claim compression remains an untested cause hypothesis. Draft prompt has not been evaluated.']}
    (out / 'audit.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    with (out / 'audit.csv').open('w', newline='') as f:
        fields = ['case_id', 'clause_id', 'requirement', 'condition', 'coverage', 'applicability', 'answer_claim_numbers', 'citation_ids', 'rationale']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, 'answer_claim_numbers': ','.join(map(str, row['answer_claim_numbers'])),
                             'citation_ids': ','.join(row['citation_ids'])})
    (out / 'draft-system.txt').write_text(system + '\n')
    for case_id, pack in packs.items():
        prompt = build_answer_prompt(pack['question'], pack)
        payload = {'system': system, 'messages': [{'role': 'user', 'content': prompt}],
                   'status': 'offline_draft_unexecuted', 'baseline_context_sha256': digest(next(
                       c['context_pack_path'] for c in config['cases'] if c['case_id'] == case_id)),
                   'requires': 'Fresh explicit model authorization and token/budget checks before execution'}
        (out / (case_id + '-draft-prompt.json')).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    for cid, values in counts.items():
        print(cid + ' reviewed clause coverage: ' + json.dumps(values))
    print('SAVED: ' + str(out))
    print('Audit JSON/CSV, draft system prompt and two unexecuted prompt payloads ready.')
    print('No model calls, retries, production prompt edits or holdout access.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
