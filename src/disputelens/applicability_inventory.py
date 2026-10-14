"""Inventory six development cases from saved evidence; no model or holdout access."""
import hashlib
import json
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .embed_batch import write_json

BASE = Path('data/indexes/answer-eval-plan/c36f49c3b45e0291a3d40299')
TRIAL = Path('data/indexes/scope-guard-trials/404df217cae1eafb43aaf6a6')
PLAN = Path('eval/experiments/applicability-v1/mapping-slice-plan.json')


def main():
    plan = json.loads(PLAN.read_text())
    protocol = json.loads((TRIAL / 'protocol-snapshot.json').read_text())
    summary = json.loads((BASE / 'claude-development-summary.json').read_text())
    dev_path = Path('eval/expanded/dev-cases.json')
    cases = json.loads(dev_path.read_text())
    selected = [c['case_id'] for c in plan['cases']]
    if selected != [c['case_id'] for c in protocol['cases']]:
        raise ModelError('Slice differs from saved experiment protocol.')
    rows = {}
    inputs = {str(PLAN): digest(PLAN), str(dev_path): digest(dev_path),
              str(TRIAL / 'protocol-snapshot.json'): digest(TRIAL / 'protocol-snapshot.json'),
              str(BASE / 'claude-development-summary.json'): digest(BASE / 'claude-development-summary.json')}
    for cid in selected:
        case = next(c for c in cases if c['case_id'] == cid and c['split'] == 'dev')
        frozen = next(c for c in protocol['cases'] if c['case_id'] == cid)
        pack_path = Path(frozen['pack_path'])
        if digest(pack_path) != frozen['pack_sha256']:
            raise ModelError('Frozen pack changed.')
        pack = json.loads(pack_path.read_text())
        if pack['question'] != case['question'] or pack['trusted_settings'] != case['filters']:
            raise ModelError('Development question/scope changed.')
        inputs[str(pack_path)] = digest(pack_path)
        evidence = {e['citation_id']: e for g in pack['groups'] for e in g['evidence']}
        wanted = {}
        baseline = next(c for c in summary['cases'] if c['case_id'] == cid)
        bp = Path(baseline['attempt_path'])
        if digest(bp) != baseline['attempt_sha256'] or digest(bp) != frozen['baseline_attempt_sha256']:
            raise ModelError('Baseline attempt changed.')
        cp = TRIAL / 'attempts' / (cid + '.json')
        candidate = json.loads(cp.read_text())
        if candidate.get('status') != 'complete_requires_review':
            raise ModelError('Candidate has no validated usable answer.')
        for path in (bp, cp):
            inputs[str(path)] = digest(path)
        for role, answer in [('baseline_cited', baseline['answer']), ('candidate_cited', candidate['answer'])]:
            for claim in answer['claims']:
                for citation in claim['citations']:
                    if citation['id'] not in evidence:
                        raise ModelError('Cited label absent from frozen pack.')
                    pid = evidence[citation['id']]['passage_id']
                    wanted.setdefault(pid, set()).add(role)
        for expected in case['expected_claims']:
            for pid in expected['supporting_passage_ids']:
                wanted.setdefault(pid, set()).add('expected_support')
        for pid, roles in wanted.items():
            pieces = [e for e in evidence.values() if e['passage_id'] == pid]
            if not pieces:
                raise ModelError('Selected support absent from pack; record retrieval gap before inventory: ' + pid)
            row = rows.setdefault(pid, {'passage_id': pid, 'occurrences': [],
                                       'mapping_disposition': 'pending_source_review'})
            row['occurrences'].append({'case_id': cid, 'selection_roles': sorted(roles),
                'pack_path': str(pack_path), 'evidence': [{'citation_id': e['citation_id'],
                'headings': e['headings'], 'text': e['text'], 'text_sha256': hashlib.sha256(e['text'].encode()).hexdigest(),
                'locator': e['locator'], 'character_start': e['evidence_character_start'],
                'character_end': e['evidence_character_end'], 'complete_evidence': e['complete_evidence']} for e in pieces]})
    out = Path('data/indexes/applicability-trials') / ('inventory-' + digest(PLAN)[:24] + '.json')
    write_json(out, {'status': 'inventory_only_source_mapping_pending', 'input_hashes': inputs,
        'runner_sha256': digest(__file__), 'case_ids': selected, 'unique_passages': len(rows),
        'passages': list(rows.values()), 'limitations': ['Gold inclusion does not authorize applicability.',
        'Mixed-scope passages may need span mapping.', 'No scope decision, filtered pack or model answer produced.']})
    print('CASES: ' + str(len(selected)) + '; UNIQUE PASSAGES: ' + str(len(rows)))
    print('SAVED: ' + str(out) + '\nHash checks passed. Source mapping pending; no model calls or holdout access.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
