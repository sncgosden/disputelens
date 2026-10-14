"""Compare bookmark-aware BM25 retrieval with the unchanged development baseline."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from .build_index import digest
from .client import ModelError
from .embed_batch import audit_chunks, loaded_embedding_model, safe_error, write_json
from .embedding_units import make_embedding_units
from .evaluate_retrieval import run_cases, summarize
from .keyword_search import BM25_CONFIG, retrieve_keyword


def compare_records(before, after):
    left = {r['case_id']: r for r in before}
    right = {r['case_id']: r for r in after}
    if (set(left) != set(right) or len(left) != len(before) or len(right) != len(after)):
        raise ModelError('Comparison requires identical unique development case IDs.')
    deltas = []
    for case_id, old in left.items():
        new = right[case_id]
        if old['question'] != new['question'] or old['filters'] != new['filters']:
            raise ModelError('Question or merchant scope changed between runs.')
        changes = {}
        for k in (5, 20):
            a = old['metrics'][str(k)]['passage_recall']
            b = new['metrics'][str(k)]['passage_recall']
            if (a is None) != (b is None):
                raise ModelError('Gold metric denominator changed between runs.')
            changes[str(k)] = None if a is None else b - a
        deltas.append({'case_id': case_id, 'recall_changes': changes})
    counts = {}
    for k in (5, 20):
        values = [d['recall_changes'][str(k)] for d in deltas
                  if d['recall_changes'][str(k)] is not None]
        counts[str(k)] = {'improved': sum(v > 1e-12 for v in values),
                         'worsened': sum(v < -1e-12 for v in values),
                         'unchanged': sum(abs(v) <= 1e-12 for v in values),
                         'scored_cases': len(values)}
    return {'direction': 'bookmark hierarchy minus original', 'counts': counts,
            'case_deltas': deltas}


def main():
    load_dotenv('.env')
    try:
        import lmstudio as lms
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case_path = Path(config['dev_cases_path'])
        cases = json.loads(case_path.read_text())
        if len(cases) != 45 or any(c['split'] != 'dev' for c in cases):
            raise ModelError('Expected the fixed 45 development cases; holdout is not loaded.')
        pointer = json.loads(Path('data/indexes/section-hierarchy/latest.json').read_text())
        experiment = json.loads(Path(pointer['experiment_path']).read_text())
        if digest(config['normalized_path']) != experiment['identity']['baseline_normalized_sha256']:
            raise ModelError('Active baseline changed after experiment preparation.')
        source_path = Path(experiment['chunk_path'])
        source = json.loads(source_path.read_text())
        if source['normalized_sha256'] != digest(experiment['normalized_path']):
            raise ModelError('Prepared chunks are stale.')
        old_pointer = json.loads(Path('data/indexes/retrieval-eval/bm25-latest.json').read_text())
        old_summary = json.loads(Path(old_pointer['summary_path']).read_text())
        old_identity = old_summary['identity']
        if (old_summary['status'] != 'complete'
                or old_identity['strategy'] != 'bm25'
                or old_identity['dev_cases_sha256'] != digest(case_path)
                or old_identity['embedding_units_sha256'] != digest(config['embedding_units_path'])
                or old_identity['metric_contract_sha256'] != digest('eval/retrieval-metric-contract.json')
                or old_identity['bm25_config'] != BM25_CONFIG):
            raise ModelError('BM25 baseline must match the unchanged cases, units and metric definitions.')
        package = Path(__file__).parent
        for name in ('keyword_search.py', 'retrieval_metrics.py', 'applicability.py'):
            if old_identity['code_sha256'][name] != digest(package / name):
                raise ModelError('Ranking, metric or applicability code changed since baseline.')
        before = []
        for case in cases:
            record = json.loads((Path(old_pointer['run_directory']) / 'cases' / (case['case_id'] + '.json')).read_text())
            if record['identity'] != old_identity:
                raise ModelError('Baseline contains mixed run configurations.')
            before.append(record)
        if os.getenv('LM_API_TOKEN'):
            raise ModelError('Pinned SDK token checking requires an unauthenticated local server.')
        baseline_units = json.loads(Path(config['embedding_units_path']).read_text())
        model_id = os.getenv('LM_EMBEDDING_MODEL')
        model = loaded_embedding_model(lms, model_id)
        limit = model.get_context_length()
        prefix = os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ')
        if (model_id != baseline_units['model'] or limit != baseline_units['context_length']
                or prefix != baseline_units['document_prefix']):
            raise ModelError('Use the baseline embedding model, prefix and loaded input capacity.')
        identity = {'strategy': 'bm25', 'experiment': 'publisher-bookmark-hierarchy',
                    'source_chunks_sha256': digest(source_path),
                    'baseline_summary_sha256': digest(old_pointer['summary_path']),
                    'dev_cases_sha256': digest(case_path), 'model_for_token_check': model_id,
                    'context_length': limit, 'document_prefix': prefix,
                    'bm25_config': BM25_CONFIG, 'top_k': 20, 'cutoffs': [5, 20],
                    'code_sha256': {name: digest(package / name) for name in (
                        'evaluate_heading_experiment.py', 'embedding_units.py',
                        'keyword_search.py', 'retrieval_metrics.py', 'applicability.py')}}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        directory = Path(experiment['directory']) / 'bm25-eval' / run_id
        units_path = directory / 'search-units.json'
        if units_path.exists():
            saved = json.loads(units_path.read_text())
            if saved['identity'] != identity:
                raise ModelError('Saved search units do not match experiment configuration.')
            units = saved['chunks']
            print(f'REUSED: {len(units)} token-safe units.', flush=True)
        else:
            print(f'TOKEN CHECK ONLY: {len(source["chunks"])} chunks; no embeddings.', flush=True)
            rows = audit_chunks(source['chunks'], model.tokenize, limit, prefix,
                lambda n, total: print(f'Checked {n}/{total}.', flush=True))
            units = make_embedding_units(source['chunks'], rows, model.tokenize, limit, prefix)
            write_json(directory / 'token-audit.json', {'identity': identity, 'chunks': rows})
            write_json(units_path, {'identity': identity, 'chunks': units})
        scoring_identity = {**identity, 'search_units_sha256': digest(units_path)}

        def compute(question, filters):
            started = time.perf_counter()
            results = retrieve_keyword(units, question, filters, 20)
            return {'results': results, 'retrieval_seconds': time.perf_counter() - started,
                    'query_embedding_calls': 0}

        after, reused = run_cases(cases, compute, units, directory, scoring_identity)
        paired = compare_records(before, after)
        baseline, updated = summarize(before), summarize(after)
        output = directory / 'comparison.json'
        write_json(output, {'status': 'complete', 'identity': scoring_identity,
            'baseline': baseline, 'bookmark_hierarchy': updated, 'paired': paired,
            'reused_cases_this_run': reused,
            'limitation': 'Hierarchy also changes heading-aware chunk boundaries. '
                          'BM25 only; vector/hybrid and section applicability not tested here.'})
        write_json(Path(experiment['directory']) / 'bm25-comparison-latest.json',
                   {'comparison_path': str(output)})
        for k in (5, 20):
            a = baseline['overall'][str(k)]['metrics']['passage_recall']['mean']
            b = updated['overall'][str(k)]['metrics']['passage_recall']['mean']
            print(f'RECALL@{k}: {a:.1%} -> {b:.1%}; ' + json.dumps(paired['counts'][str(k)]))
        by_id = {r['case_id']: r for r in after}
        for case_id in ('E03', 'E14', 'E17', 'E18'):
            row = by_id[case_id]
            print(f'{case_id}: recall@5 {row["metrics"]["5"]["passage_recall"]:.0%}; '
                  f'recall@20 {row["metrics"]["20"]["passage_recall"]:.0%}')
        print(f'SAVED: {output}\nAll 45 development cases scored. '
              'Original index preserved. No embeddings, chat calls, holdout or GitHub sync.')
    except KeyboardInterrupt:
        print('Stopped. Rerun the same command to resume saved cases.', file=sys.stderr)
        return 1
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
