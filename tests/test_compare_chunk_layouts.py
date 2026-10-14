import pytest

from disputelens.client import ModelError
from disputelens.compare_chunk_layouts import paired_changes


def record(case_id, recall):
    return {'case_id': case_id, 'question': case_id, 'filters': {'corpus': 'real'},
            'metrics': {str(k): {'passage_recall': recall} for k in (5, 20)}}


def test_pairing_uses_case_ids_and_keeps_opposing_changes_visible():
    before = [record('a', 0), record('b', 1)]
    after = [record('b', 0), record('a', 1)]
    comparison = paired_changes(before, after)
    assert comparison['counts']['5'] == {'improved': 1, 'worsened': 1, 'unchanged': 0, 'scored_cases': 2}
    assert comparison['case_deltas'][0]['recall_changes']['5'] == 1


def test_mismatched_population_or_scope_is_rejected():
    with pytest.raises(ModelError):
        paired_changes([record('a', 1)], [record('b', 1)])
    other = record('a', 1)
    other['filters']['corpus'] = 'fixture'
    with pytest.raises(ModelError):
        paired_changes([record('a', 1)], [other])
