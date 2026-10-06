from contextlib import closing

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from disputelens.applicability import applicable
from disputelens.verify_index import scenarios
from disputelens.verify_retrieval_filters import check_methods


def test_all_methods_match_applicability_across_adversarial_scopes():
    base = {'corpus': 'real', 'provider': 'Stripe', 'scheme': None, 'status': 'snapshot'}
    variants = [{}, {'provider': 'Adyen'}, {'provider': 'Square', 'region': 'UK'},
                {'provider': 'PayPal', 'region': 'UK'}, {'provider': None, 'scheme': 'Visa'},
                {'provider': None, 'scheme': 'Mastercard', 'region': 'multiple'},
                {'status': 'superseded'}, {'region': 'US'},
                {'corpus': 'fixture', 'provider': 'DisputeLens fictional provider', 'status': 'current'},
                {'corpus': 'fixture', 'provider': 'DisputeLens fictional provider', 'status': 'superseded'},
                {'provider': None, 'scheme': None, 'region': 'global'}]
    units = [{'chunk_id': str(n), 'text': 'dispute evidence response', 'metadata': {**base, **v}}
             for n, v in enumerate(variants)]
    with closing(QdrantClient(':memory:')) as client:
        client.create_collection('test', vectors_config=VectorParams(size=2, distance=Distance.COSINE))
        client.upsert('test', points=[PointStruct(id=n, vector=[1., 0.], payload=u)
                                     for n, u in enumerate(units)])
        for label, filters in scenarios():
            expected = {u['chunk_id'] for u in units if applicable(u['metadata'], **filters)}
            count, methods = check_methods(client, 'test', units, [1., 0.],
                                           'dispute evidence', filters, top_k=20)
            assert count == len(expected), label
            for method, results in methods.items():
                assert {r['unit']['chunk_id'] for r in results} == expected, (label, method)
