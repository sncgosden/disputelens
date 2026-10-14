import json
from pathlib import Path

import pytest

from disputelens import fresh_mastercard as fm
from disputelens.client import ModelError


def test_cases_file_has_twelve_unique_mastercard_cases():
    cases = fm.load_cases()
    assert len(cases) == 12 and len({c['case_id'] for c in cases}) == 12


def test_require_refuses_without_preconditions(tmp_path, monkeypatch):
    monkeypatch.setattr(fm, 'PRECONDITIONS', tmp_path / 'missing.json')
    protocol = json.loads(fm.PROTOCOL.read_text())
    with pytest.raises(ModelError):
        fm.require(protocol)


def test_budget_must_match_protocol(tmp_path, monkeypatch):
    path = tmp_path / 'p.json'
    path.write_text(json.dumps({'go_ahead': {'by': 'Sebastian', 'authorised': True, 'at': 'x', 'words': 'y'},
                                'budget': {'max_calls': 15, 'max_usd': 2.0}, 'review_plan': 'independent'}))
    monkeypatch.setattr(fm, 'PRECONDITIONS', path)
    st = fm.preconditions(json.loads(fm.PROTOCOL.read_text()))
    assert st['budget'][0] is False and st['go_ahead'][0] is True


def rows(*items):
    return [{'case': 'F', 'claim': i + 1, 'v2': v, 'semantic': s} for i, (v, s) in enumerate(items)]


def test_score_inconclusive_when_few_wrong_claims():
    r = fm.score_rows(rows((True, True), (False, False)), {'F': ['no', 'yes']})
    assert r['decision'] == 'inconclusive_on_safety'


def test_score_semantic_candidate_when_safe_and_fewer_needless_flags():
    items = [(True, True)] * 3 + [(True, False)] * 4 + [(False, False)]
    labels = {'F': ['no'] * 3 + ['yes'] * 4 + ['yes']}
    r = fm.score_rows(rows(*items), labels)
    assert r['decision'] == 'semantic_is_a_shipping_candidate'


def test_score_v2_stays_when_semantic_misses_a_wrong_claim():
    items = [(True, True), (True, True), (True, False), (True, False)]
    labels = {'F': ['no', 'no', 'no', 'yes']}
    r = fm.score_rows(rows(*items), labels)
    assert r['decision'] == 'v2_stays_default' and r['semantic']['wrong_missed'] == 1


def test_unsure_is_never_counted_as_yes_or_no():
    r = fm.score_rows(rows((True, True)), {'F': ['unsure']})
    assert r['v2']['unsure'] == 1 and r['v2']['applies_flagged'] == 0 and r['v2']['wrong_caught'] == 0
