"""Resumable evaluation of the fixed development set; never loads holdout cases."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient

from .build_index import checked_vectors, digest
from .client import ModelError, configured_models
from .embed_batch import loaded_embedding_model, safe_error, write_json
from .hybrid_search import fuse_rankings
from .keyword_search import BM25_CONFIG, retrieve_keyword
from .retrieval_metrics import score_retrieval
from .semantic_search import retrieve


def query_type(question):
    return 'exact_code' if re.search(r'\b(?:1[0-3]\.\d+(?:\.\d+)?|48\d{2})\b', question) else 'no_explicit_code'


def metric_means(records, cutoff):
    fields = ('passage_recall', 'fractional_passage_recall', 'gold_passage_precision', 'ndcg')
    scores = [r['metrics'][str(cutoff)] for r in records]
    metrics = {}
    for field in fields:
        values = [s[field] for s in scores if s[field] is not None]
        metrics[field] = {'mean': sum(values)/len(values) if values else None, 'cases': len(values)}
    return {'case_count': len(records), 'metrics': metrics,
            'cases_with_all_expected_evidence': sum(s['all_expected_evidence_retrieved'] is True for s in scores),
            'cases_with_gold': sum(not s['no_gold_case'] for s in scores),
            'no_gold_cases': sum(s['no_gold_case'] for s in scores),
            'cases_missing_gold_from_applicable_corpus': sum(bool(s['missing_gold_from_applicable_corpus']) for s in scores)}


def summarize(records):
    slices = {}
    for field in ('corpus', 'provider', 'scheme', 'query_type'):
        groups = {}
        for record in records:
            value = record['query_type'] if field == 'query_type' else record['filters'].get(field)
            label = str(value) if value is not None else 'unspecified'
            groups.setdefault(label, []).append(record)
        slices[field] = {label: {str(k): metric_means(rows, k) for k in (5, 20)}
                         for label, rows in groups.items()}
    seconds = [r['retrieval_seconds'] for r in records]
    return {'overall': {str(k): metric_means(records, k) for k in (5, 20)},
            'slices': slices,
            'retrieval_latency_seconds': {'median': float(np.median(seconds)) if seconds else None,
                'p90': float(np.percentile(seconds, 90)) if seconds else None,
                'cases': len(seconds), 'basis': 'Original per-case retrieval time; excludes setup and scoring.'},
            'incomplete_evidence_case_ids_at_5': [r['case_id'] for r in records
                if r['metrics']['5']['all_expected_evidence_retrieved'] is False]}


def run_cases(cases, compute, units, directory, identity):
    if any(c['split'] != 'dev' for c in cases):
        raise ModelError('This runner accepts development cases only.')
    if len({c['case_id'] for c in cases}) != len(cases):
        raise ModelError('Duplicate development case IDs.')
    records, reused = [], 0
    for n, case in enumerate(cases, 1):
        case_path = directory / 'cases' / (case['case_id'] + '.json')
        if case_path.exists():
            record = json.loads(case_path.read_text())
            if record['identity'] != identity or record['question'] != case['question'] or record['filters'] != case['filters']:
                raise ModelError('Saved case does not match the frozen evaluation configuration.')
            reused += 1
            print(f'REUSED: {n}/{len(cases)} {case["case_id"]}', flush=True)
        else:
            print(f'RUNNING: {n}/{len(cases)} {case["case_id"]}', flush=True)
            # compute sees only question/settings. Expected evidence enters scoring afterwards.
            result = compute(case['question'], case['filters'])
            record = {'identity': identity, 'case_id': case['case_id'], 'question': case['question'],
                'filters': case['filters'], 'query_type': query_type(case['question']),
                **result,
                'metrics': {str(k): score_retrieval(result['results'], case, units, k) for k in (5, 20)}}
            write_json(case_path, record)
            score = record['metrics']['5']
            recall = score['passage_recall']
            print(f'SAVED: {case["case_id"]}; recall@5: {recall:.0%}' if recall is not None
                  else f'SAVED: {case["case_id"]}; no-gold case retained separately.', flush=True)
        records.append(record)
        write_json(directory / 'progress.json', {'identity': identity,
            'completed': len(records), 'expected': len(cases),
            'status': 'running' if len(records) < len(cases) else 'all_cases_saved'})
    return records, reused


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strategy', choices=['vector', 'bm25', 'hybrid'], default='vector')
    args = parser.parse_args()
    models, client = configured_models(), None
    try:
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case_path = Path(config['dev_cases_path'])
        cases = json.loads(case_path.read_text())
        if len(cases) != 45 or any(c['split'] != 'dev' for c in cases):
            raise ModelError('Expected exactly 45 development cases. Holdout cases must remain separate.')
        manifest_path = Path('data/indexes/index-manifest.json')
        manifest = json.loads(manifest_path.read_text())
        if (manifest['status'] != 'complete'
                or manifest['model'] != os.getenv('LM_EMBEDDING_MODEL')
                or manifest['document_prefix'] != os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ')
                or digest(manifest['embedding_units_path']) != manifest['embedding_units_sha256']):
            raise ModelError('Index or embedding configuration changed. Rebuild before evaluating.')
        unit_data = json.loads(Path(manifest['embedding_units_path']).read_text())
        if digest(unit_data['source_chunk_path']) != unit_data['source_chunks_sha256']:
            raise ModelError('Source chunks changed. Rebuild the search units and index.')
        units = unit_data['chunks']
        query_prefix = os.getenv('EMBED_QUERY_PREFIX', 'search_query: ')
        package = Path(__file__).parent
        identity = {'strategy': args.strategy, 'dev_cases_sha256': digest(case_path),
            'embedding_units_sha256': manifest['embedding_units_sha256'],
            'index_manifest_sha256': digest(manifest_path), 'model': manifest['model'],
            'query_prefix': query_prefix, 'document_prefix': manifest['document_prefix'],
            'top_k': 20, 'cutoffs': [5, 20], 'candidate_k': 20,
            'bm25_config': BM25_CONFIG if args.strategy != 'vector' else None,
            'rrf_constant': 60 if args.strategy == 'hybrid' else None,
            'metric_contract_sha256': digest('eval/retrieval-metric-contract.json'),
            'code_sha256': {name: digest(package / name) for name in (
                'evaluate_retrieval.py', 'retrieval_metrics.py', 'semantic_search.py',
                'keyword_search.py', 'hybrid_search.py', 'applicability.py', 'client.py')}}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        directory = Path('data/indexes/retrieval-eval') / (args.strategy + '-' + run_id)
        client = QdrantClient(path=manifest['qdrant_path']) if args.strategy != 'bm25' else None
        embedding_model = None
        if args.strategy != 'bm25':
            import lmstudio as lms
            from urllib.parse import urlparse
            if urlparse(models.base).hostname not in ('localhost', '127.0.0.1', '::1') or os.getenv('LM_API_TOKEN'):
                raise ModelError('This run needs unauthenticated local LM Studio for SDK token checks.')
            embedding_model = loaded_embedding_model(lms, manifest['model'])
            context_length = embedding_model.get_context_length()

        def compute(question, filters):
            started = time.perf_counter()
            candidates = None
            if args.strategy == 'bm25':
                results = retrieve_keyword(units, question, filters, 20)
            else:
                if len(embedding_model.tokenize(query_prefix + question)) + 8 > context_length:
                    raise ModelError('A development question exceeds the loaded embedding limit.')
                vector = checked_vectors(models.embed([question], kind='query'), 1, manifest['dimension'])[0].tolist()
                results = retrieve(client, manifest['collection_name'], vector, filters, 20)
                if args.strategy == 'hybrid':
                    keywords = retrieve_keyword(units, question, filters, 20)
                    candidates = {'vector': results, 'bm25': keywords}
                    results = fuse_rankings(results, keywords, 20)
            return {'results': results, 'component_candidates': candidates,
                    'retrieval_seconds': time.perf_counter()-started,
                    'query_embedding_calls': 0 if args.strategy == 'bm25' else 1}

        print(f'DEVELOPMENT ONLY: {len(cases)} cases; strategy {args.strategy}; top 20, scored at 5 and 20.', flush=True)
        print('Gold is consulted after retrieval. Successful cases are saved for resume.', flush=True)
        started = time.perf_counter()
        records, reused = run_cases(cases, compute, units, directory, identity)
        summary = {'identity': identity, 'status': 'complete', 'expected_cases': 45,
            'completed_cases': len(records), 'reused_cases_this_run': reused,
            'wall_seconds_this_run': time.perf_counter()-started,
            'setup_and_model_loading_excluded_from_case_latency': True,
            'warmup_call_performed': False, **summarize(records)}
        write_json(directory / 'summary.json', summary)
        pointer = Path('data/indexes/retrieval-eval') / (args.strategy + '-latest.json')
        write_json(pointer, {'summary_path': str(directory / 'summary.json'), 'run_directory': str(directory)})
        for k in (5, 20):
            metrics = summary['overall'][str(k)]['metrics']
            formatted = '; '.join(f'{name} {data["mean"]:.1%} (n={data["cases"]})'
                for name, data in metrics.items() if data['mean'] is not None)
            print(f'AT {k}: {formatted}')
        print(f'PASS: {len(records)}/45 cases saved and scored; resumed cases: {reused}.')
        print(f'SAVED SUMMARY: {directory / "summary.json"}')
        print('Per-case failures and segment counts retained. No holdout, generation, Claude calls or GitHub sync.')
    except KeyboardInterrupt:
        print('\nStopped. Rerun the same command to resume completed cases.', file=sys.stderr)
        return 1
    except Exception as error:
        print(f'STOP: {safe_error(error)}', file=sys.stderr)
        print('The run is incomplete. Successful cases remain saved; rerun after fixing the cause.', file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
        models.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
