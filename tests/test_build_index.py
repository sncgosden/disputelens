import json
from contextlib import closing

import numpy as np
import pytest
from qdrant_client import QdrantClient

from disputelens.build_index import index_units, checked_vectors
from disputelens.client import ModelError


def test_interrupted_run_resumes_and_preserves_payload(tmp_path):
    units = [{'chunk_id': str(n), 'text': 'Evidence ' + str(n),
              'parent_chunk_id': 'original', 'metadata': {'provider': 'Stripe'},
              'evidence': [{'locator': {'pdf_page': 2}, 'complete_evidence': False}]}
             for n in range(3)]
    calls = []
    def interrupted(texts):
        calls.append(texts)
        if len(calls) == 2:
            raise ModelError('Simulated connection failure')
        return np.array([[1., 0., 0.]] * len(texts))
    identity = {'model': 'test-only', 'embedding_units_sha256': 'fixture'}
    with closing(QdrantClient(path=str(tmp_path / 'qdrant'))) as client:
        with pytest.raises(ModelError, match='Simulated'):
            index_units(units, interrupted, client, tmp_path, identity, 3, batch_size=2)
    assert not (tmp_path / 'index-manifest.json').exists()
    resumed = []
    def embed(texts):
        resumed.extend(texts)
        return np.array([[1., 0., 0.]] * len(texts))
    with closing(QdrantClient(path=str(tmp_path / 'qdrant'))) as client:
        result = index_units(units, embed, client, tmp_path, identity, 3, batch_size=2)
        assert resumed == ['Evidence 2']
        assert result['cached_embeddings_this_run'] == 2
        assert result['points'] == 3
        points, _ = client.scroll(result['collection_name'], limit=10, with_payload=True)
        assert all(p.payload['parent_chunk_id'] == 'original' for p in points)
        assert all(p.payload['evidence'][0]['locator']['pdf_page'] == 2 for p in points)
        assert json.loads((tmp_path / 'index-manifest.json').read_text())['status'] == 'complete'


def test_corrupt_vectors_are_rejected():
    for vectors in ([[0., 0.]], [[float('nan'), 1.]], [[1., 0., 0.]]):
        with pytest.raises(ModelError):
            checked_vectors(vectors, 1, 2)
