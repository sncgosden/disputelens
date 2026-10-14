import hashlib
import json
from contextlib import closing

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

from disputelens.client import ModelError
from disputelens.scoped_vector_search import point_id, retrieve_scoped
from disputelens.section_scope import classify_section


def manifest():
    m = {'schema_version': '1.0', 'embedding_units_path': 'units.json',
         'embedding_units_sha256': 'hash', 'model': 'nomic',
         'document_prefix': 'search_document: ', 'dimension': 2}
    run_id = hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()
    return {**m, 'collection_name': 'disputelens_' + run_id[:24]}


def unit(name):
    return {'chunk_id': name, 'passage_ids': [name], 'metadata': {
        'source_id': 'mastercard-chargeback-guide', 'corpus': 'real', 'provider': None,
        'scheme': 'Mastercard', 'region': 'multiple', 'status': 'snapshot'}}


FILTERS = {'corpus': 'real', 'provider': 'Stripe', 'scheme': 'Mastercard', 'region': 'UK'}


def test_disallowed_high_similarity_points_cannot_take_top_k_slots():
    m = manifest()
    rows = [unit('maestro'), unit('qr'), unit('valid')]
    scopes = {'maestro': classify_section(['Non-Mastercard BIN Maestro']),
              'qr': classify_section(['Mastercard Merchant Presented QR']),
              'valid': classify_section(['Refund Not Processed'])}
    with closing(QdrantClient(':memory:')) as client:
        client.create_collection(m['collection_name'], vectors_config=VectorParams(size=2, distance=Distance.COSINE))
        client.upsert(m['collection_name'], points=[
            PointStruct(id=point_id(m, row['chunk_id']), vector=vector, payload=row)
            for row, vector in zip(rows, [[1., 0.], [.99, .01], [.6, .8]])])
        results = retrieve_scoped(client, m, [1., 0.], FILTERS, [rows[2]], scopes, top_k=1)
        assert results[0]['unit']['chunk_id'] == 'valid'
        with pytest.raises(ModelError, match='allowlist'):
            retrieve_scoped(client, m, [1., 0.], FILTERS, rows, scopes, top_k=1)
        assert retrieve_scoped(client, m, [1., 0.], FILTERS, [], scopes, top_k=1) == []


def test_changed_collection_identity_is_rejected():
    m = manifest()
    m['collection_name'] = 'different'
    with pytest.raises(ModelError, match='stable point-ID'):
        point_id(m, 'valid')
