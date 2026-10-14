import numpy as np

from disputelens import scope_detector_semantic as sd


def test_clean_removes_parentheses_and_nbsp():
    assert sd.clean('Refund Not Processed (4853)') == 'Refund Not Processed'


def test_nearest_margin():
    titles = ['a', 'b', 'c']
    vecs = np.array([[1, 0], [0, 1], [0.8, 0.6]])
    best, sim, margin = sd.nearest([1, 0], vecs, titles)
    assert best == 'a' and abs(sim - 1) < 1e-9 and abs(margin - 0.2) < 1e-9


def test_established_requires_all_three():
    assert sd.is_established('a', 'a', 0.7, 0.05, 0.6, 0.02)
    assert not sd.is_established('a', 'b', 0.9, 0.5, 0.6, 0.02)
    assert not sd.is_established('a', 'a', 0.5, 0.5, 0.6, 0.02)
    assert not sd.is_established('a', 'a', 0.7, 0.01, 0.6, 0.02)


def test_decide_keeps_phrases_only_when_established():
    base = ['4853', 'stand-in']
    assert sd.decide(base, True) == ['stand-in']
    assert sd.decide(base, False) == base
    assert sd.decide([], True) == []


def row(label, sim, margin, base=('4853',), own='a', best='a'):
    return {'label': label, 'own': own, 'best': best, 'sim': sim, 'margin': margin, 'base': list(base)}


def test_selection_prefers_full_recall_then_fewer_false_flags_then_larger_tau():
    rows = [row('unscoped', 0.55, 0.01), row('unscoped', 0.9, 0.001, own='a', best='b'), row('scoped', 0.8, 0.1), row('scoped', 0.52, 0.05)]
    pick = sd.select(sd.score_grid(rows))
    assert pick['unscoped_flagged'] == 2
    assert pick['scoped_false_flags'] == 0
    assert pick['tau'] == 0.50 and pick['delta'] == 0.05


def test_selection_falls_back_to_most_unscoped_flagged():
    rows = [row('unscoped', 0.9, 0.5), row('scoped', 0.9, 0.5)]
    pick = sd.select(sd.score_grid(rows))
    assert pick['unscoped_flagged'] == 0 and pick['scoped_false_flags'] == 0
