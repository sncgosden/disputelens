"""Check retained quoted extracts, not semantic claim entailment or accuracy."""
import hashlib
import json
from pathlib import Path

from .applicability_slice_trial import load_slice
from .build_index import digest
from .client import ModelError
from .embed_batch import write_json
from .experimental_applicability import decide_applicability


def normalize(text):
    return ' '.join(text.split())


def main():
    config, originals = load_slice()
    maps = {m['passage_id']:m for m in config['maps']}
    protocol_path=Path('data/indexes/scope-guard-trials/404df217cae1eafb43aaf6a6/protocol-snapshot.json')
    protocol=json.loads(protocol_path.read_text())
    rows=[]
    for case in protocol['cases']:
        pack=json.loads(Path(case['pack_path']).read_text())
        evidence={e['citation_id']:e for g in pack['groups'] for e in g['evidence']}
        original={k:v for k,v in pack['trusted_settings'].items() if k!='corpus'}
        for role,path in [('baseline',Path(case['baseline_attempt_path'])),
                          ('candidate',protocol_path.parent/'attempts'/(case['case_id']+'.json'))]:
            saved=json.loads(path.read_text())
            for n,claim in enumerate(saved['answer']['claims'],1):
                checks=[]
                for cite in claim['citations']:
                    e=evidence[cite['id']];m=maps[e['passage_id']]
                    text=e['text'][m['span_start']:m['span_end']]
                    checks.append({'citation_id':cite['id'],'passage_id':e['passage_id'],
                                   'quote_retained':normalize(cite['quote']) in normalize(text),
                                   'original_scope_decision':decide_applicability(m,original)['decision'],
                                   'matching_fixture_decision':decide_applicability(m,m['requirements'])['decision']})
                rows.append({'case_id':case['case_id'],'role':role,'claim_number':n,
                             'claim_text':claim['text'],'citation_checks':checks,
                             'all_quotes_retained':all(c['quote_retained'] for c in checks),
                             'semantic_entailment':'not established by quote retention'})
    supplement_path=Path('eval/experiments/applicability-v1/E23-linked-exception-context.json')
    supplement=json.loads(supplement_path.read_text())
    if digest(supplement['normalized_path'])!=supplement['normalized_sha256']:
        raise ModelError('Supplement source changed.')
    for piece in supplement['passages']:
        if hashlib.sha256(piece['text'].encode()).hexdigest()!=piece['text_sha256']:
            raise ModelError('Supplement text changed.')
    summary={'claims_checked':len(rows),'claims_all_quotes_retained':sum(x['all_quotes_retained'] for x in rows),
             'semantic_accuracy':'not measured','promotion':'blocked_semantic_and_independent_review_gates'}
    out=Path('data/indexes/applicability-trials')/('retained-support-'+digest('eval/experiments/applicability-v1/reviewed-slice-map.json')[:24]+'.json')
    write_json(out,{'summary':summary,'rows':rows,'runner_sha256':digest(__file__),
                    'supplement_sha256':digest(supplement_path),
                    'limitations':['Exact extract retention cannot establish all claim clauses supported.',
                    'Matching settings are simulated, not original merchant facts.',
                    'E23 supplemental context was not in original frozen generation evidence.']})
    print(json.dumps(summary))
    print('SAVED: '+str(out)+'\nNo model calls or frozen pack changes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
