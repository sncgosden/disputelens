import json
from pathlib import Path

import pytest

from disputelens.client import ModelError
from disputelens.experimental_applicability import decide_applicability

FIXTURES = json.loads((Path(__file__).resolve().parents[1] /
    'eval/experiments/applicability-v1/fixtures.json').read_text())


@pytest.mark.parametrize('case', FIXTURES['fixtures'], ids=lambda c: c['fixture_id'])
def test_preregistered_scope_decisions(case):
    source = {**FIXTURES['source_scope'], 'review_status': 'reviewed'}
    result = decide_applicability(source, case['trusted_scope'])
    assert result['decision'] == case['expected_decision']
    if 'expected_missing' in case:
        assert result['missing'] == case['expected_missing']


def test_unreviewed_map_cannot_authorize_advice():
    source = {'requirements': {'scheme': 'Mastercard'}, 'review_status': 'pending'}
    assert decide_applicability(source, {'scheme': 'Mastercard'})['decision'] == 'unreviewed'


def test_country_does_not_establish_membership_and_false_is_a_conflict():
    source = {'review_status': 'reviewed', 'requirements': {'participating_countries_membership': True}}
    assert decide_applicability(source, {'region': 'UK'})['decision'] == 'requires_clarification'
    assert decide_applicability(source, {'participating_countries_membership': False})['decision'] == 'inapplicable'
    assert decide_applicability(source, {'participating_countries_membership': True})['decision'] == 'applicable'


@pytest.mark.parametrize('settings', [{'participating_countries_membership': 'true'},
                                     {'participating_countries_membership': 1},
                                     {'scheme': ''}, {'inferred_country': 'UK'}])
def test_invalid_trusted_scope_is_rejected(settings):
    source = {'review_status': 'reviewed', 'requirements': {'scheme': 'Mastercard'}}
    with pytest.raises(ModelError):
        decide_applicability(source, settings)


def test_matching_specialized_scope_is_not_required_for_reviewed_general_guidance():
    source = {'review_status': 'reviewed', 'requirements': {'scheme': 'Mastercard', 'dispute_subtype': None}}
    assert decide_applicability(source, {'scheme': 'Mastercard'})['decision'] == 'applicable'


def test_empty_reviewed_requirements_cannot_silently_authorize_evidence():
    with pytest.raises(ModelError):
        decide_applicability({'review_status': 'reviewed', 'requirements': {}}, {})
