import pytest

from disputelens.client import ModelError
from disputelens.evaluate_context import coverage_score, retention_change


def test_complete_and_partial_evidence_have_distinct_scores():
    score = coverage_score([
        {'covered_characters': 10, 'total_characters': 10, 'fully_retrieved': True},
        {'covered_characters': 5, 'total_characters': 10, 'fully_retrieved': False}])
    assert score['passage_recall'] == .5
    assert score['fractional_passage_recall'] == .75
    assert not score['all_expected_evidence']


def test_context_loss_is_reported_and_invented_recovery_rejected():
    assert retention_change({'passage_recall': 1}, {'passage_recall': .5}) == 'lost_evidence'
    assert retention_change({'passage_recall': .5}, {'passage_recall': .5}) == 'unchanged'
    assert retention_change(coverage_score([]), coverage_score([])) == 'no_gold'
    with pytest.raises(ModelError, match='absent'):
        retention_change({'passage_recall': .5}, {'passage_recall': 1})
    with pytest.raises(ModelError, match='denominator'):
        retention_change({'passage_recall': None}, {'passage_recall': 1})
