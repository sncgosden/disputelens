import pytest

from disputelens.query_transform import transform_query, fuse_queries


def test_preserves_original_and_code_while_adding_recurring_terms():
    q = 'I canceled a subscription; the notice says 4853.'
    result = transform_query(q)
    assert result['original'] == q
    assert result['expanded'].startswith(q + '\n')
    assert result['applied_rules'] == ['recurring']
    assert 'cancelled recurring transaction' in result['expanded']


def test_refund_arrival_not_confused_with_goods_nonreceipt():
    result = transform_query('My promised refund never arrived.')
    assert result['applied_rules'] == ['refund']
    assert 'goods or services' not in result['expanded']


def test_pending_refund_does_not_infer_nonprocessing():
    q = 'My refund is pending. How many days?'
    assert transform_query(q)['expanded'] == q


def test_unmatched_query_unchanged_and_no_authority_fields_added():
    q = 'Can I edit my submitted response?'
    result = transform_query(q)
    assert result == {'original': q, 'expanded': q, 'applied_rules': []}


def test_fusion_deduplicates_and_preserves_both_ranking_traces():
    def row(rank, key):
        return {'rank': rank, 'unit': {'chunk_id': key, 'text': key}, 'bm25_score': 1}
    original = [row(1, 'a'), row(2, 'b')]
    expanded = [row(1, 'b'), row(2, 'c')]
    result = fuse_queries(original, expanded)
    assert [r['unit']['chunk_id'] for r in result] == ['b', 'a', 'c']
    assert result[0]['query_ranks'] == {'original': 2, 'expanded': 1}
    assert len(original) == 2 and original[0]['rank'] == 1


def test_fusion_rejects_conflicting_payload_for_same_unit():
    with pytest.raises(ValueError, match='conflicting payloads'):
        fuse_queries([{'rank': 1, 'unit': {'chunk_id': 'a', 'text': 'first'}}],
                     [{'rank': 1, 'unit': {'chunk_id': 'a', 'text': 'changed'}}])


def test_fusion_does_not_guarantee_all_union_candidates_survive_cutoff():
    original = [{'rank': 1, 'unit': {'chunk_id': 'a'}}]
    expanded = [{'rank': 1, 'unit': {'chunk_id': 'b'}}]
    assert len(fuse_queries(original, expanded, top_k=1)) == 1
