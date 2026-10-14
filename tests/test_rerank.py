import json

import pytest

from disputelens.client import ModelError
from disputelens.rerank import apply_order, build_prompt


FILTERS = {'corpus': 'real', 'provider': 'Stripe', 'scheme': 'Visa', 'region': 'UK'}


def candidates():
    return [{'rank': rank, 'rrf_score': 1 / (60 + rank), 'unit': {
        'chunk_id': name,
        'metadata': {'corpus': 'real', 'provider': 'Stripe', 'scheme': 'Visa',
                     'region': 'UK', 'status': 'snapshot'},
        'headings': ['Refund rules'], 'text': 'Full evidence ' + name,
        'evidence': [{'passage_id': name, 'locator': 'source#page=1'}],
    }} for rank, name in enumerate(['a', 'b', 'c'], 1)]


def test_prompt_has_full_text_and_scope_but_no_gold_or_original_scores():
    rows = candidates()
    rows[0]['unit']['text'] = 'x' * 20000
    rows[0]['expected_answer'] = 'SECRET GOLD'
    prompt = build_prompt('Which evidence?', rows, FILTERS)
    data = json.loads(prompt)
    assert data['candidates'][0]['text'] == 'x' * 20000
    assert data['trusted_settings'] == FILTERS
    assert 'SECRET GOLD' not in prompt
    assert 'rrf_score' not in prompt


def test_order_preserves_original_evidence_and_records_rank_changes():
    rows = candidates()
    output = apply_order('{"ordered_ids":["c","a","b"]}', rows, top_k=2)
    assert [r['unit']['chunk_id'] for r in output] == ['c', 'a']
    assert [r['pre_rerank_rank'] for r in output] == [3, 1]
    assert output[0]['unit'] is rows[2]['unit']
    assert output[0]['rrf_score'] == rows[2]['rrf_score']
    assert rows[2]['rank'] == 3


@pytest.mark.parametrize('text', [
    '{"ordered_ids":["a","b"]}',
    '{"ordered_ids":["a","a","c"]}',
    '{"ordered_ids":["a","b","invented"]}',
    '{"ordered_ids":["a","b",3]}',
    '{"ordered_ids":["a","b","c"],"confidence":0.9}',
    '{"ordered_ids":["a","b","c"],"ordered_ids":["c","b","a"]}',
    '```json\n{"ordered_ids":["a","b","c"]}\n```',
])
def test_invalid_model_output_stops_instead_of_silent_fallback(text):
    with pytest.raises(ModelError, match='Invalid reranker JSON'):
        apply_order(text, candidates(), top_k=3)


def test_selection_cannot_exceed_candidate_pool():
    with pytest.raises(ModelError, match='top-k must fit'):
        apply_order('{"ordered_ids":["a","b","c"]}', candidates(), top_k=5)


def test_wrong_provider_is_rejected_before_prompt_and_duplicates_rejected():
    rows = candidates()
    rows[0]['unit']['metadata']['provider'] = 'Adyen'
    with pytest.raises(ModelError, match='applicability'):
        build_prompt('Evidence?', rows, FILTERS)
    rows = candidates()
    rows[1]['unit']['chunk_id'] = 'a'
    with pytest.raises(ModelError, match='unique'):
        build_prompt('Evidence?', rows, FILTERS)
