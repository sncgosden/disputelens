"""Verify persisted public-guidance filtering independently of embedding quality."""
import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient

from .applicability import applicable
from .build_index import digest
from .client import ModelError
from .semantic_search import scope_filter, retrieve


def verify_scope(client, collection, units, filters):
    expected = {u['chunk_id'] for u in units if applicable(u['metadata'], **filters)}
    actual, offset = set(), None
    while True:
        points, offset = client.scroll(collection, scroll_filter=scope_filter(**filters),
            limit=256, offset=offset, with_payload=['chunk_id', 'metadata'], with_vectors=False)
        for point in points:
            if not applicable(point.payload['metadata'], **filters):
                raise ModelError('Qdrant admitted an inapplicable source.')
            actual.add(point.payload['chunk_id'])
        if offset is None:
            break
    if actual != expected:
        raise ModelError(f'Filter mismatch: {len(actual-expected)} unexpected units; '
                         f'{len(expected-actual)} missing units.')
    return len(actual)


def scenarios():
    settings = {'corpus': 'real', 'provider': 'Stripe', 'scheme': 'Visa', 'region': 'UK'}
    return [
        ('Stripe / Visa / UK', settings),
        ('Adyen / Visa / UK', {**settings, 'provider': 'Adyen'}),
        ('Square / Visa / UK', {**settings, 'provider': 'Square'}),
        ('PayPal / Visa / UK', {**settings, 'provider': 'PayPal'}),
        ('Stripe / Mastercard / UK', {**settings, 'scheme': 'Mastercard'}),
        ('Missing provider / Visa / UK', {**settings, 'provider': None}),
        ('Missing scheme / Stripe / UK', {**settings, 'scheme': None}),
        ('Missing provider and scheme', {**settings, 'provider': None, 'scheme': None}),
        ('Square / Visa / US', {**settings, 'provider': 'Square', 'region': 'US'}),
        ('Square / Visa / missing region', {**settings, 'provider': 'Square', 'region': None}),
        ('Fictional controlled policies', {**settings, 'corpus': 'fixture',
                                          'provider': 'DisputeLens fictional provider'}),
    ]


def main():
    try:
        manifest_path = Path('data/indexes/index-manifest.json')
        manifest = json.loads(manifest_path.read_text())
        if manifest['status'] != 'complete':
            raise ModelError('Complete indexing before this check.')
        if digest(manifest['embedding_units_path']) != manifest['embedding_units_sha256']:
            raise ModelError('Search units changed. Rebuild the index before checking.')
        units = json.loads(Path(manifest['embedding_units_path']).read_text())['chunks']
        checks, searches = [], []
        vector = None
        for reopening in range(2):
            client = QdrantClient(path=manifest['qdrant_path'])
            try:
                count = client.count(manifest['collection_name'], exact=True).count
                if count != len(units) or count != manifest['points']:
                    raise ModelError('Persisted point count does not match the index manifest.')
                if vector is None:
                    points, _ = client.scroll(manifest['collection_name'], limit=1,
                                              with_vectors=True, with_payload=False)
                    vector = points[0].vector
                    if not isinstance(vector, list) or len(vector) != manifest['dimension']:
                        raise ModelError('Persisted vector dimensions do not match the manifest.')
                print(f'Open {reopening+1}: {count} persisted points.', flush=True)
                for name, filters in scenarios():
                    allowed = verify_scope(client, manifest['collection_name'], units, filters)
                    checks.append({'open': reopening+1, 'scenario': name,
                                   'filters': filters, 'eligible_units': allowed, 'passed': True})
                    print(f'PASS: {name}: {allowed} eligible units; exact agreement with applicability.py.', flush=True)
                results = retrieve(client, manifest['collection_name'], vector,
                                   scenarios()[0][1], top_k=5)
                searches.append([(r['unit']['chunk_id'], r['similarity']) for r in results])
            finally:
                client.close()
        if searches[0] != searches[1]:
            raise ModelError('Search results changed after reopening the persisted index.')
        output = Path('data/indexes/filter-verification.json')
        output.write_text(json.dumps({'index_manifest_sha256': digest(manifest_path),
            'collection': manifest['collection_name'], 'checks': checks,
            'search_repeatability_passed': True,
            'scope': 'Public source applicability; private tenant authorization requires separate tests.'},
            indent=2) + '\n')
        print('PASS: filtered search results identical after closing and reopening Qdrant.')
        print(f'SAVED: {output}')
        print('No embeddings, generation, Claude calls or GitHub sync.')
    except Exception as error:
        print(f'STOP: {type(error).__name__}: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
