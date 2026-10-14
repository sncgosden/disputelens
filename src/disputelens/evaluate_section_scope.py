"""Evaluate explicit section exclusions with original chunks and fixed dev gold."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from qdrant_client import QdrantClient

from .build_index import digest, checked_vectors
from .client import ModelError, configured_models
from .embed_batch import safe_error, write_json
from .evaluate_heading_experiment import compare_records
from .evaluate_retrieval import run_cases, summarize
from .keyword_search import BM25_CONFIG, retrieve_keyword
from .section_scope import classify_section, section_applicable
from .hybrid_search import fuse_rankings
from .scoped_vector_search import retrieve_scoped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strategy', choices=['bm25', 'vector', 'hybrid'], default='bm25')
    args = parser.parse_args()
    models, client = None, None
    try:
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case_path = Path(config['dev_cases_path'])
        cases = json.loads(case_path.read_text())
        if len(cases) != 45 or any(c['split'] != 'dev' for c in cases):
            raise ModelError('Only the fixed 45 development cases are allowed.')
        heading_pointer = json.loads(Path('data/indexes/section-hierarchy/latest.json').read_text())
        experiment = json.loads(Path(heading_pointer['experiment_path']).read_text())
        if digest(config['normalized_path']) != experiment['identity']['baseline_normalized_sha256']:
            raise ModelError('The original normalized baseline changed.')
        documents = json.loads(Path(experiment['normalized_path']).read_text())['documents']
        original = json.loads(Path(config['normalized_path']).read_text())['documents']
        # Only headings from the prepared experiment may differ.
        from .prepare_heading_experiment import evidence_signature
        if evidence_signature(documents) != evidence_signature(original):
            raise ModelError('Prepared heading map differs in evidence or source scope.')
        scopes = {b['passage_id']: classify_section(b['headings'])
                  for d in documents if d['parent_id'] == 'mastercard-chargeback-guide'
                  for b in d['blocks']}
        units_path = Path(config['embedding_units_path'])
        units = json.loads(units_path.read_text())['chunks']
        old_pointer = json.loads(Path(f'data/indexes/retrieval-eval/{args.strategy}-latest.json').read_text())
        old_summary = json.loads(Path(old_pointer['summary_path']).read_text())
        old_identity = old_summary['identity']
        package = Path(__file__).parent
        if (old_summary['status'] != 'complete' or old_identity['strategy'] != args.strategy
                or old_identity['embedding_units_sha256'] != digest(units_path)
                or old_identity['dev_cases_sha256'] != digest(case_path)
                or old_identity['bm25_config'] != (None if args.strategy == 'vector' else BM25_CONFIG)
                or old_identity['metric_contract_sha256'] != digest('eval/retrieval-metric-contract.json')):
            raise ModelError('Baseline cases, units or metric settings changed.')
        for name in ('keyword_search.py', 'retrieval_metrics.py', 'applicability.py',
                     'semantic_search.py', 'hybrid_search.py', 'client.py'):
            if old_identity['code_sha256'][name] != digest(package / name):
                raise ModelError('Baseline ranking, scoring or document-scope code changed.')
        before = []
        for case in cases:
            row = json.loads((Path(old_pointer['run_directory']) / 'cases' / (case['case_id'] + '.json')).read_text())
            if row['identity'] != old_identity:
                raise ModelError('Baseline contains mixed configurations.')
            before.append(row)
        manifest = json.loads(Path('data/indexes/index-manifest.json').read_text())
        if (manifest['status'] != 'complete'
                or manifest['embedding_units_sha256'] != digest(units_path)
                or manifest['points'] != len(units)
                or old_identity['index_manifest_sha256'] != digest('data/indexes/index-manifest.json')):
            raise ModelError('Active index differs from the original baseline.')
        embedding_model, query_prefix, context_length = None, None, None
        if args.strategy != 'bm25':
            models = configured_models()
            import lmstudio as lms
            from .embed_batch import loaded_embedding_model
            if urlparse(models.base).hostname not in ('localhost', '127.0.0.1', '::1') or os.getenv('LM_API_TOKEN'):
                raise ModelError('This experiment needs unauthenticated local LM Studio token checks.')
            query_prefix = os.getenv('EMBED_QUERY_PREFIX', 'search_query: ')
            if (manifest['model'] != os.getenv('LM_EMBEDDING_MODEL')
                    or query_prefix != old_identity['query_prefix']
                    or manifest['document_prefix'] != os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ')):
                raise ModelError('Embedding configuration differs from baseline.')
            embedding_model = loaded_embedding_model(lms, manifest['model'])
            context_length = embedding_model.get_context_length()
            client = QdrantClient(path=manifest['qdrant_path'])
            if client.count(manifest['collection_name'], exact=True).count != len(units):
                raise ModelError('Qdrant point count differs from the baseline.')
        identity = {'experiment': 'explicit-section-exclusions-v1', 'strategy': args.strategy,
                    'embedding_units_sha256': digest(units_path),
                    'section_documents_sha256': digest(experiment['normalized_path']),
                    'dev_cases_sha256': digest(case_path),
                    'baseline_summary_sha256': digest(old_pointer['summary_path']),
                    'payment_rail': None,
                    'rail_policy': 'Unspecified trusted payment rail excludes QR-specific guidance; no query inference.',
                    'top_k': 20, 'cutoffs': [5, 20],
                    'bm25_config': None if args.strategy == 'vector' else BM25_CONFIG,
                    'candidate_k_per_method': 20, 'rrf_constant': 60 if args.strategy == 'hybrid' else None,
                    'index_manifest_sha256': digest('data/indexes/index-manifest.json'),
                    'query_prefix': query_prefix, 'context_length': context_length,
                    'code_sha256': {name: digest(package / name) for name in (
                        'section_scope.py', 'evaluate_section_scope.py',
                        'keyword_search.py', 'retrieval_metrics.py', 'applicability.py',
                        'scoped_vector_search.py', 'hybrid_search.py', 'client.py')}}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        directory = Path('data/indexes/section-scope') / run_id
        write_json(directory / 'passage-scope-map.json', {'identity': identity, 'passages': scopes})

        def compute(question, filters):
            started = time.perf_counter()
            # Filter before building lexical statistics and before the result cutoff.
            eligible = [u for u in units if section_applicable(u, filters, scopes)]
            candidates = None
            embedding_calls = 0
            if args.strategy == 'bm25':
                results = retrieve_keyword(eligible, question, filters, 20)
            else:
                if len(embedding_model.tokenize(query_prefix + question)) + 8 > context_length:
                    raise ModelError('Development query exceeds the loaded embedding input limit.')
                query_identity = {'question': question, 'model': manifest['model'],
                                  'prefix': query_prefix, 'dimension': manifest['dimension'],
                                  'context_length': context_length,
                                  'client_code_sha256': digest(package / 'client.py')}
                key = hashlib.sha256(json.dumps(query_identity, sort_keys=True).encode()).hexdigest()
                cache = Path('data/indexes/section-scope/query-embeddings') / (key + '.json')
                if cache.exists():
                    saved = json.loads(cache.read_text())
                    if saved['identity'] != query_identity:
                        raise ModelError('Cached query vector configuration mismatch.')
                    vector = checked_vectors([saved['vector']], 1, manifest['dimension'])[0].tolist()
                else:
                    vector = checked_vectors(models.embed([question], kind='query'),
                                             1, manifest['dimension'])[0].tolist()
                    embedding_calls = 1
                    write_json(cache, {'identity': query_identity, 'vector': vector})
                results = retrieve_scoped(client, manifest, vector, filters, eligible, scopes, 20)
                if args.strategy == 'hybrid':
                    keywords = retrieve_keyword(eligible, question, filters, 20)
                    candidates = {'vector': results, 'bm25': keywords}
                    results = fuse_rankings(results, keywords, 20)
            if any(not section_applicable(r['unit'], filters, scopes) for r in results):
                raise ModelError('Section scope verification failed.')
            return {'results': results, 'retrieval_seconds': time.perf_counter() - started,
                    'query_embedding_calls': embedding_calls, 'component_candidates': candidates,
                    'section_eligible_units': len(eligible)}

        # Score against the ORIGINAL applicable corpus: newly excluded gold is a
        # measured recall loss, never removed from the evaluation denominator.
        after, reused = run_cases(cases, compute, units, directory, identity)
        paired = compare_records(before, after)
        baseline, updated = summarize(before), summarize(after)
        output = directory / 'comparison.json'
        write_json(output, {'status': 'complete', 'identity': identity,
            'baseline': baseline, 'section_scoped': updated, 'paired': paired,
            'reused_cases_this_run': reused,
            'scope_checks_passed': True,
            'limitations': ['Only two explicit section exclusions; full applicability is not established.',
                           'QR is absent from trusted dev settings, not inferred from question text.',
                           'Filtering changes eligible-corpus BM25 statistics; no chunk-text changes.',
                           'Existing Qdrant vectors are reused with a pre-ranking ID allowlist.',
                           'Query-cache reuse changes timing; these timings are not a fair uncached speed benchmark.',
                           'No active-index changes or private-data authorization.']})
        write_json(Path('data/indexes/section-scope/latest.json'), {'comparison_path': str(output)})
        write_json(Path(f'data/indexes/section-scope/{args.strategy}-latest.json'), {'comparison_path': str(output)})
        for k in (5, 20):
            a = baseline['overall'][str(k)]['metrics']['passage_recall']['mean']
            b = updated['overall'][str(k)]['metrics']['passage_recall']['mean']
            print(f'RECALL@{k}: {a:.1%} -> {b:.1%}; ' + json.dumps(paired['counts'][str(k)]))
        by_id = {r['case_id']: r for r in after}
        for case_id in ('E14', 'E15', 'E18', 'E19'):
            row = by_id[case_id]
            print(f'{case_id}: recall@5 {row["metrics"]["5"]["passage_recall"]:.0%}; '
                  f'recall@20 {row["metrics"]["20"]["passage_recall"]:.0%}')
        print(f'PASS: all returned units satisfy the explicit section guards. SAVED: {output}')
        print('All 45 cases scored with unchanged gold. Active index preserved. '
              'No document embeddings, generation, holdout or GitHub sync.')
        if args.strategy != 'bm25':
            print('Local Nomic query embeddings only; cached vectors are shared between vector and hybrid runs.')
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
        if models is not None:
            models.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
