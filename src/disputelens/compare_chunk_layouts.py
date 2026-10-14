"""Paired BM25 chunk-layout comparison with fixed gold and token capacity."""
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
from .keyword_search import retrieve_keyword, BM25_CONFIG


def paired_changes(records_400, records_250):
    left = {r['case_id']: r for r in records_400}
    right = {r['case_id']: r for r in records_250}
    if set(left) != set(right) or len(left) != len(records_400) or len(right) != len(records_250):
        raise ModelError('Chunk comparison must contain the same unique development cases.')
    deltas = []
    for case_id, a in left.items():
        b = right[case_id]
        if a['question'] != b['question'] or a['filters'] != b['filters']:
            raise ModelError('Question or filters changed between chunk layouts.')
        deltas.append({'case_id': case_id, 'recall_changes': {str(k):
            None if a['metrics'][str(k)]['passage_recall'] is None or b['metrics'][str(k)]['passage_recall'] is None
            else b['metrics'][str(k)]['passage_recall']-a['metrics'][str(k)]['passage_recall']
            for k in (5, 20)}})
    counts = {}
    for k in (5, 20):
        values = [d['recall_changes'][str(k)] for d in deltas if d['recall_changes'][str(k)] is not None]
        counts[str(k)] = {'improved': sum(v > 1e-12 for v in values),
                         'worsened': sum(v < -1e-12 for v in values),
                         'unchanged': sum(abs(v) <= 1e-12 for v in values), 'scored_cases': len(values)}
    return {'direction': '250 minus 400', 'counts': counts, 'case_deltas': deltas}


def main():
    load_dotenv('.env')
    try:
        import lmstudio as lms
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case_path = Path(config['dev_cases_path'])
        cases = json.loads(case_path.read_text())
        if len(cases) != 45 or any(c['split'] != 'dev' for c in cases):
            raise ModelError('Expected exactly 45 development cases; no holdout may be included.')
        if os.getenv('LM_API_TOKEN'):
            raise ModelError('The pinned SDK requires unauthenticated local token checks.')
        model_id = os.getenv('LM_EMBEDDING_MODEL')
        model = loaded_embedding_model(lms, model_id)
        limit = model.get_context_length()
        prefix = os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ')
        baseline = json.loads(Path(config['embedding_units_path']).read_text())
        if (model_id != baseline['model'] or limit != baseline['context_length']
                or prefix != baseline['document_prefix']):
            raise ModelError('Use the same embedding model, prefix and loaded capacity as the existing baseline.')
        normalized_hash = digest(config['normalized_path'])
        paths = {}
        for entry in config['chunk_paths']:
            path = Path(entry)
            data = json.loads(path.read_text())
            if data['normalized_sha256'] != normalized_hash:
                raise ModelError('A chunk layout is stale. Rebuild it from the current normalized documents.')
            sizes = {u['config']['target_words'] for u in data['chunks']}
            if len(sizes) != 1:
                raise ModelError('Mixed word targets within a chunk layout.')
            paths[sizes.pop()] = (path, data)
        if set(paths) != {250, 400}:
            raise ModelError('Need exactly the 250-word and 400-word source layouts.')
        package = Path(__file__).parent
        common = {'strategy': 'bm25', 'dev_cases_sha256': digest(case_path),
            'normalized_sha256': normalized_hash, 'embedding_model_for_capacity_check': model_id,
            'context_length': limit, 'document_prefix': prefix, 'bm25_config': BM25_CONFIG,
            'top_k': 20, 'cutoffs': [5, 20], 'metric_contract_sha256': digest('eval/retrieval-metric-contract.json'),
            'source_chunk_sha256': {str(words): digest(path) for words, (path, _) in paths.items()},
            'code_sha256': {name: digest(package / name) for name in ('compare_chunk_layouts.py',
                'embedding_units.py', 'embed_batch.py', 'evaluate_retrieval.py',
                'keyword_search.py', 'retrieval_metrics.py', 'applicability.py')}}
        run_id = hashlib.sha256(json.dumps(common, sort_keys=True).encode()).hexdigest()[:24]
        root = Path('data/indexes/chunk-comparison') / run_id
        summaries, records_by_words = {}, {}
        for words in (400, 250):
            path, layout = paths[words]
            directory = root / str(words)
            units_path = directory / 'search-units.json'
            if units_path.exists():
                units = json.loads(units_path.read_text())['chunks']
                print(f'REUSED: {words}-word layout, {len(units)} token-safe units.', flush=True)
            else:
                print(f'CHECKING: {words}-word layout; {len(layout["chunks"])} original chunks.', flush=True)
                rows = audit_chunks(layout['chunks'], model.tokenize, limit, prefix,
                    lambda n, total: print(f'Checked {n}/{total}.', flush=True))
                units = make_embedding_units(layout['chunks'], rows, model.tokenize, limit, prefix)
                write_json(directory / 'token-audit.json', {'context_length': limit, 'chunks': rows})
                write_json(units_path, {'identity': common, 'word_target': words,
                    'source_chunk_sha256': digest(path), 'chunks': units})
                print(f'PASS: {len(units)} units fit; original text retained.', flush=True)
            identity = {**common, 'word_target': words, 'search_units_sha256': digest(units_path)}
            def compute(question, filters):
                started = time.perf_counter()
                results = retrieve_keyword(units, question, filters, 20)
                return {'results': results, 'retrieval_seconds': time.perf_counter()-started,
                        'query_embedding_calls': 0}
            records, reused = run_cases(cases, compute, units, directory, identity)
            summary = {'identity': identity, 'status': 'complete', 'completed_cases': len(records),
                       'reused_cases_this_run': reused, 'search_units': len(units), **summarize(records)}
            write_json(directory / 'summary.json', summary)
            summaries[str(words)] = summary
            records_by_words[words] = records
        paired = paired_changes(records_by_words[400], records_by_words[250])
        output = root / 'comparison.json'
        write_json(output, {'status': 'complete', 'common_settings': common,
            'layouts': summaries, 'paired_recall_changes': paired,
            'interpretation': 'NDCG ideals vary by layout; use paired passage recall and context coverage '
                              'alongside ranking metrics. This comparison does not measure generation quality.'})
        write_json(Path('data/indexes/chunk-comparison/latest.json'), {'comparison_path': str(output)})
        for words, summary in summaries.items():
            print(f'\n{words}-WORD TARGET: {summary["search_units"]} search units; 45 cases.')
            for k in (5, 20):
                metrics = summary['overall'][str(k)]['metrics']
                print(f'AT {k}: recall {metrics["passage_recall"]["mean"]:.1%}; '
                      f'gold precision {metrics["gold_passage_precision"]["mean"]:.1%}; '
                      f'NDCG {metrics["ndcg"]["mean"]:.1%}')
        print('PAIRED RECALL CHANGES: ' + json.dumps(paired['counts']))
        print(f'PASS: both layouts scored on the same 45 development cases. SAVED: {output}')
        print('Tokenization only for input checks; no new embeddings, Claude calls, holdout or GitHub sync.')
    except KeyboardInterrupt:
        print('\nStopped. Rerun the same command to resume.', file=sys.stderr)
        return 1
    except Exception as error:
        print(f'STOP: {safe_error(error)}', file=sys.stderr)
        print('Comparison incomplete; saved cases can be resumed with the same command.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
