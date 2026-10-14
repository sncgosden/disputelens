"""Offline diagnosis only: flag selected unresolved scopes without filtering evidence."""
import json
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .embed_batch import write_json


def unresolved_scope(headings, trusted=None):
    """Experimental narrow flags, not a complete applicability classifier.

    Membership must be explicitly established; a country string alone is insufficient.
    Specific refund sections require an explicit reviewed heading path, not a model guess.
    No flags means no issue identified by these two rules, not verified applicability.
    """
    trusted = trusted or {}
    issues = []
    if any('participating countries' in h.casefold() for h in headings):
        if trusted.get('participating_countries_membership') is not True:
            issues.append('Participating Countries membership not explicitly established')
    if any(h.casefold() == 'refund previously issued' for h in headings):
        if trusted.get('reviewed_refund_section_path') != list(headings):
            issues.append('Reason-code-specific refund section applicability not explicitly established')
    return issues


def main():
    protocol_path = Path('eval/experiments/scope-guard-v1/protocol.json')
    protocol = json.loads(protocol_path.read_text())
    rows = []
    for case in protocol['cases']:
        path = Path(case['pack_path'])
        if digest(path) != case['pack_sha256']:
            raise ModelError('Frozen pack changed.')
        pack = json.loads(path.read_text())
        evidence = [e for g in pack['groups'] for e in g['evidence']]
        flagged = []
        for e in evidence:
            issues = unresolved_scope(e['headings'])
            if issues:
                flagged.append({'citation_id': e['citation_id'], 'passage_id': e['passage_id'],
                                'headings': e['headings'], 'issues': issues})
        rows.append({'case_id': case['case_id'], 'evidence_count': len(evidence),
                     'flagged_count': len(flagged), 'flagged': flagged})
        print(f'{case["case_id"]}: {len(flagged)}/{len(evidence)} extracts have unresolved targeted scope')
    output = Path('data/indexes/scope-guard-trials') / ('scope-audit-' + digest(protocol_path)[:24] + '.json')
    write_json(output, {'status': 'diagnostic_only', 'protocol_sha256': digest(protocol_path),
                        'audit_code_sha256': digest(__file__), 'cases': rows,
                        'limitations': ['No evidence filtered, no answer generated, no holdout loaded.',
                                        'Flags identify missing proof of applicability, not proven inapplicability.',
                                        'These two rules are not a complete scope or semantic checker.',
                                        'Flagging can remove useful general facts if later used blindly as a filter; coverage must be measured first.']})
    print('SAVED: ' + str(output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
