"""Offline paired BM25 expansion/multi-query experiment on all 45 dev questions."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .embed_batch import safe_error, write_json
from .evaluate_focused_context import find_bm25
from .evaluate_heading_experiment import compare_records
from .evaluate_retrieval import run_cases, summarize
from .keyword_search import BM25_CONFIG, retrieve_keyword
from .query_transform import transform_query, fuse_queries
from .section_scope import section_applicable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['expanded', 'multi'], default='expanded')
    args = parser.parse_args()
    try:
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case_path = Path(config['dev_cases_path'])
        cases = json.loads(case_path.read_text())
        if len(cases) != 45 or any(c['split'] != 'dev' for c in cases):
            raise ModelError('Expected fixed 45 development cases only.')
        hp = json.loads(Path('data/indexes/section-scope/hybrid-latest.json').read_text())
        hybrid_path = Path(hp['comparison_path'])
        hybrid = json.loads(hybrid_path.read_text())
        baseline_path = find_bm25(hybrid['identity'])
        baseline = json.loads(baseline_path.read_text())
        old = baseline['identity']
        package = Path(__file__).parent
        if (old['dev_cases_sha256'] != digest(case_path)
                or old['embedding_units_sha256'] != digest(config['embedding_units_path'])
                or old['bm25_config'] != BM25_CONFIG):
            raise ModelError('Baseline cases, units or BM25 configuration changed.')
        for name in ('section_scope.py', 'keyword_search.py', 'retrieval_metrics.py', 'applicability.py'):
            if old['code_sha256'][name] != digest(package / name):
                raise ModelError('Baseline ranking, scope or scoring code changed.')
        units = json.loads(Path(config['embedding_units_path']).read_text())['chunks']
        scope_map = json.loads((baseline_path.parent / 'passage-scope-map.json').read_text())
        if scope_map['identity'] != old:
            raise ModelError('Baseline scope map identity mismatch.')
        before = []
        for c in cases:
            record = json.loads((baseline_path.parent / 'cases' / (c['case_id'] + '.json')).read_text())
            if record['identity'] != old or record['question'] != c['question'] or record['filters'] != c['filters']:
                raise ModelError('Baseline case identity/question/scope mismatch.')
            before.append(record)
        identity = {'experiment': 'terminology-expansion-bm25-v2', 'strategy': 'bm25',
                    'mode': args.mode, 'candidate_k_per_query': 20,
                    'rrf_constant': 60 if args.mode == 'multi' else None,
                    'baseline_sha256': digest(baseline_path), 'dev_cases_sha256': digest(case_path),
                    'embedding_units_sha256': digest(config['embedding_units_path']),
                    'scope_map_sha256': digest(baseline_path.parent / 'passage-scope-map.json'),
                    'metric_contract_sha256': digest('eval/retrieval-metric-contract.json'),
                    'top_k': 20, 'bm25_config': BM25_CONFIG,
                    'code_sha256': {name: digest(package / name) for name in (
                        'query_transform.py', 'evaluate_query_transform.py', 'keyword_search.py',
                        'section_scope.py', 'retrieval_metrics.py', 'semantic_search.py')}}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        directory = Path('data/indexes/query-transform') / run_id

        def compute(question, filters):
            started = time.perf_counter()
            transformed = transform_query(question)
            eligible = [u for u in units if section_applicable(u, filters, scope_map['passages'])]
            results = retrieve_keyword(eligible, transformed['expanded'], filters, 20)
            components = None
            if args.mode == 'multi' and transformed['expanded'] != question:
                original_results = retrieve_keyword(eligible, question, filters, 20)
                components = {'original': original_results, 'expanded': results}
                results = fuse_queries(original_results, results, 20)
            if any(not section_applicable(r['unit'], filters, scope_map['passages']) for r in results):
                raise ModelError('Transformed query bypassed scope.')
            return {'results': results, 'query_transform': transformed,
                    'component_candidates': components,
                    'retrieval_seconds': time.perf_counter() - started}

        after, reused = run_cases(cases, compute, units, directory, identity)
        original_summary, transformed_summary = summarize(before), summarize(after)
        paired = compare_records(before, after)
        paired['direction'] = args.mode + ' query retrieval minus original query retrieval'
        output = directory / 'comparison.json'
        write_json(output, {'status': 'complete', 'identity': identity,
            'baseline': original_summary, 'transformed': transformed_summary, 'paired': paired,
            'reused_cases_this_run': reused,
            'limitations': ['Development-informed terminology rules; not a blind benchmark.',
                           'Keyword retrieval only; no claim of hybrid improvement.',
                           'Multi-query union may recover evidence that is then lost at the fused cutoff.',
                           'Terms are search hints, not inferred facts or provider/scheme permissions.',
                           'No runtime gold selection and no promotion.']})
        write_json(Path('data/indexes/query-transform/latest.json'), {'comparison_path': str(output)})
        for k in (5, 20):
            a = original_summary['overall'][str(k)]['metrics']['passage_recall']['mean']
            b = transformed_summary['overall'][str(k)]['metrics']['passage_recall']['mean']
            print(f'RECALL@{k}: {a:.1%} -> {b:.1%}; ' + json.dumps(paired['counts'][str(k)]))
        for row in after:
            if row['case_id'] in ('E17', 'E18'):
                print(f'{row["case_id"]}: recall@5 {row["metrics"]["5"]["passage_recall"]:.0%}; '
                      f'recall@20 {row["metrics"]["20"]["passage_recall"]:.0%}')
        print(f'SAVED: {output}')
        print('All 45 dev cases scored. No model calls, holdout, active index changes or GitHub sync.')
        return 0
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
