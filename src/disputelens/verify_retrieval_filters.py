"""Check shared applicability across vector, BM25 and hybrid retrieval."""
import json
import os
import sys
from pathlib import Path

from qdrant_client import QdrantClient

from .applicability import applicable
from .build_index import checked_vectors, digest
from .client import ModelError, configured_models
from .embed_batch import safe_error, write_json
from .hybrid_search import fuse_rankings
from .keyword_search import retrieve_keyword, BM25_CONFIG
from .semantic_search import retrieve
from .verify_index import scenarios, verify_scope


def check_methods(client, collection, units, vector, question, filters, top_k=20):
    eligible = verify_scope(client, collection, units, filters)
    vector_results = retrieve(client, collection, vector, filters, top_k)
    keyword_results = retrieve_keyword(units, question, filters, top_k)
    methods = {'vector': vector_results, 'bm25': keyword_results,
               'hybrid': fuse_rankings(vector_results, keyword_results, top_k)}
    for name, results in methods.items():
        if any(not applicable(r['unit']['metadata'], **filters) for r in results):
            raise ModelError(f'{name} returned inapplicable guidance.')
        if len({r['unit']['chunk_id'] for r in results}) != len(results):
            raise ModelError(f'{name} returned duplicate units.')
    return eligible, methods


def compact_trace(results):
    return [{**{k: v for k, v in result.items() if k != 'unit'},
        'chunk_id': result['unit']['chunk_id'],
        'parent_chunk_id': result['unit'].get('parent_chunk_id'),
        'metadata': result['unit']['metadata'],
        'passage_ids': result['unit'].get('passage_ids', [])} for result in results]


def main():
    models, client = configured_models(), None
    try:
        path = Path('data/indexes/index-manifest.json')
        manifest = json.loads(path.read_text())
        if (manifest['status'] != 'complete'
                or digest(manifest['embedding_units_path']) != manifest['embedding_units_sha256']
                or manifest['model'] != os.getenv('LM_EMBEDDING_MODEL')
                or manifest['document_prefix'] != os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ')):
            raise ModelError('Index or embedding configuration changed. Rebuild before checking.')
        units = json.loads(Path(manifest['embedding_units_path']).read_text())['chunks']
        question = 'What evidence should a merchant submit when responding to a chargeback dispute?'
        print('Embedding one short filter-test question with local Nomic...', flush=True)
        vector = checked_vectors(models.embed([question], kind='query'), 1, manifest['dimension'])[0].tolist()
        client = QdrantClient(path=manifest['qdrant_path'])
        if client.count(manifest['collection_name'], exact=True).count != len(units):
            raise ModelError('Persisted point count does not match the search units.')
        checks = []
        for label, filters in scenarios():
            eligible, methods = check_methods(client, manifest['collection_name'], units,
                                               vector, question, filters)
            for name, results in methods.items():
                checks.append({'scenario': label, 'method': name, 'question': question,
                    'filters': filters, 'eligible_units': eligible, 'passed': True,
                    'returned_candidates': compact_trace(results)})
                print(f'PASS: {name} / {label}: {len(results)} results; no inapplicable units.', flush=True)
        output = Path('data/indexes/shared-filter-verification.json')
        write_json(output, {'index_manifest_sha256': digest(path),
            'embedding_units_sha256': manifest['embedding_units_sha256'],
            'embedding_model': manifest['model'],
            'query_prefix': os.getenv('EMBED_QUERY_PREFIX', 'search_query: '),
            'top_k': 20, 'bm25_config': BM25_CONFIG,
            'fusion_config': {'rank_constant': 60, 'weights': {'vector': 1, 'bm25': 1}},
            'checks': checks,
            'purpose': 'Public source applicability checks, not retrieval-quality or private-tenant authorization evaluation.'})
        print(f'PASS: {len(checks)} method/scenario checks; question, filters and candidate IDs saved.')
        print(f'SAVED: {output}')
        print('One local query embedding; no generation, Claude calls or GitHub sync.')
    except Exception as error:
        print(f'STOP: {safe_error(error)}', file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
        models.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
