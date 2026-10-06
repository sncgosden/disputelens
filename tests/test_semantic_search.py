from contextlib import closing

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

from disputelens.semantic_search import retrieve, evidence_coverage
from disputelens.verify_index import verify_scope


def test_wrong_provider_scheme_region_and_fixture_excluded_before_top_k():
    settings = {'corpus': 'real', 'provider': 'Stripe', 'scheme': 'Visa', 'region': 'UK'}
    metadata = [
        {'corpus': 'real', 'provider': 'Adyen', 'scheme': None, 'status': 'snapshot'},
        {'corpus': 'real', 'provider': None, 'scheme': 'Mastercard', 'status': 'snapshot'},
        {'corpus': 'fixture', 'provider': 'Stripe', 'scheme': None, 'status': 'current'},
        {'corpus': 'real', 'provider': 'Stripe', 'scheme': None, 'status': 'superseded'},
        {'corpus': 'real', 'provider': 'Stripe', 'scheme': None, 'status': 'snapshot', 'region': 'US'},
        {'corpus': 'real', 'provider': 'Stripe', 'scheme': None, 'status': 'snapshot'},
        {'corpus': 'real', 'provider': None, 'scheme': 'Visa', 'status': 'snapshot', 'region': 'multiple'},
    ]
    with closing(QdrantClient(':memory:')) as client:
        client.create_collection('test', vectors_config=VectorParams(size=2, distance=Distance.COSINE))
        client.upsert('test', points=[PointStruct(id=n, vector=[1., 0.] if n < 5 else [.8, .6],
                                               payload={'chunk_id': str(n), 'metadata': m})
                                      for n, m in enumerate(metadata)])
        # Invalid passages have higher similarity; they must be excluded before the limit.
        assert {r['unit']['chunk_id'] for r in retrieve(client, 'test', [1., 0.], settings, 2)} == {'5', '6'}
        units = [{'chunk_id': str(n), 'metadata': m} for n, m in enumerate(metadata)]
        assert verify_scope(client, 'test', units, settings) == 2
        unspecified = {**settings, 'provider': None, 'scheme': None}
        assert retrieve(client, 'test', [1., 0.], unspecified, 10) == []
        assert verify_scope(client, 'test', units, unspecified) == 0


def test_partial_and_overlapping_evidence_does_not_receive_full_credit():
    def result(rank, start, end):
        return {'rank': rank, 'unit': {'passage_ids': ['p'], 'evidence': [{
            'passage_id': 'p', 'original_evidence_characters': 10,
            'evidence_character_start': start, 'evidence_character_end': end}]}}
    units = [result(1, 0, 10)['unit']]
    coverage = evidence_coverage([result(1, 0, 5), result(2, 3, 8)], ['p'], units)[0]
    assert coverage['covered_characters'] == 8
    assert not coverage['fully_retrieved']
    assert evidence_coverage([result(1, 0, 5), result(2, 5, 10)], ['p'], units)[0]['fully_retrieved']
    assert evidence_coverage([], ['p'], units)[0]['covered_characters'] == 0
