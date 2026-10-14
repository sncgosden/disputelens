import copy

import pytest

from disputelens.client import ModelError
from disputelens.evaluate_heading_experiment import compare_records


def record(name, recall):
    return {'case_id': name, 'question': name, 'filters': {'scheme': 'Visa'},
            'metrics': {str(k): {'passage_recall': recall} for k in (5, 20)}}


def test_comparison_pairs_ids_and_keeps_regressions_and_no_gold_cases():
    before = [record('a', 0), record('b', 1), record('c', None)]
    after = [record('c', None), record('b', .5), record('a', 1)]
    paired = compare_records(before, after)
    assert paired['counts']['5'] == {'improved': 1, 'worsened': 1, 'unchanged': 0, 'scored_cases': 2}
    assert paired['case_deltas'][2]['recall_changes']['5'] is None


def test_changed_scope_or_case_denominator_stops_comparison():
    before = [record('a', 1)]
    changed = copy.deepcopy(before)
    changed[0]['filters']['scheme'] = 'Mastercard'
    with pytest.raises(ModelError, match='scope'):
        compare_records(before, changed)
    with pytest.raises(ModelError, match='IDs'):
        compare_records(before, before + before)
    with pytest.raises(ModelError, match='denominator'):
        compare_records(before, [record('a', None)])
