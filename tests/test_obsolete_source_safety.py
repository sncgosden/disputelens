"""Offline retrieval-to-prompt boundary for an obsolete-only corpus."""
from contextlib import closing
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from disputelens.client import ModelError
from disputelens.context_pack import build_context
from disputelens.grounded_answer import build_answer_prompt
from disputelens.semantic_search import retrieve


def test_obsolete_only_evidence_cannot_reach_answer_prompt():
    filters = {'corpus': 'fixture', 'provider': 'Synthetic', 'scheme': None, 'region': None}
    with closing(QdrantClient(':memory:')) as client:
        client.create_collection('obsolete', vectors_config=VectorParams(size=2, distance=Distance.COSINE))
        client.upsert('obsolete', points=[PointStruct(id=1, vector=[1., 0.], payload={
            'chunk_id': 'old', 'metadata': {**filters, 'status': 'superseded'}})])
        results = retrieve(client, 'obsolete', [1., 0.], filters)
    assert results == []
    pack = build_context(results, filters, {})
    assert pack['text'] == '' and pack['citations'] == {}
    with pytest.raises(ModelError, match='No evidence in the context pack'):
        build_answer_prompt('What evidence is required?', pack)
