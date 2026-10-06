import pytest

from disputelens.client import ModelError
from disputelens.hybrid_search import fuse_rankings


def ranked(ids, key):
    return [{'rank': n, key: 1000-n, 'unit': {'chunk_id': name, 'text': name}}
            for n, name in enumerate(ids, 1)]


def test_fusion_deduplicates_and_keeps_evidence_from_either_method():
    vector = ranked(['a', 'b'], 'similarity')
    keyword = ranked(['b', 'c'], 'bm25_score')
    results = fuse_rankings(vector, keyword, top_k=3)
    assert [r['unit']['chunk_id'] for r in results] == ['b', 'a', 'c']
    assert results[0]['rrf_score'] == pytest.approx(1/62 + 1/61)
    assert results[0]['component_ranks'] == {'vector': 2, 'bm25': 1}
    assert results[1]['component_ranks']['bm25'] is None
    # Raw score magnitudes cannot affect rank fusion.
    for result in keyword:
        result['bm25_score'] *= 1000000
    changed = fuse_rankings(vector, keyword, top_k=3)
    assert [(r['unit']['chunk_id'], r['rrf_score']) for r in changed] == [
        (r['unit']['chunk_id'], r['rrf_score']) for r in results]


def test_duplicates_and_inconsistent_payloads_are_rejected():
    with pytest.raises(ModelError, match='unique'):
        fuse_rankings(ranked(['a', 'a'], 'similarity'), [])
    keyword = ranked(['a'], 'bm25_score')
    keyword[0]['unit']['text'] = 'changed'
    with pytest.raises(ModelError, match='different payloads'):
        fuse_rankings(ranked(['a'], 'similarity'), keyword)
