import json
import pytest

from disputelens.client import ModelError
from disputelens.second_review import SELECTED, SYSTEM, build_inputs, parse_review, render_answer

ANSWER = {'status': 'answered', 'claims': [{'text': 'A', 'citations': [{'id': 'S001', 'quote': 'q'}]}], 'missing_information': []}


def case(case_id, status='citation_valid_requires_review'):
    return {'case_id': case_id, 'question': f'Q {case_id}', 'trusted_filters': {'corpus': 'real'}, 'saved_status': status,
            'answer': ANSWER, 'attempt_sha256': 'a', 'context_pack_sha256': 'c',
            'review': {'correctness': 2, 'rationale': 'PREVIOUS-RATING'},
            'frozen_context_pack': {'text': f'[SOURCE1] evidence {case_id}'}}


def test_inputs_are_blinded_and_ordered():
    inputs = build_inputs({'cases': [case(c) for c in SELECTED]})
    assert [i['case_id'] for i in inputs] == SELECTED
    for item in inputs:
        assert 'PREVIOUS-RATING' not in item['user'] and 'gold' not in item['user'].lower()
        assert 'cites S001' in item['user'] and item['input_sha256']


def test_missing_or_failed_cases_are_rejected():
    with pytest.raises(ModelError):
        build_inputs({'cases': [case('E13')]})
    with pytest.raises(ModelError):
        build_inputs({'cases': [case(c, 'generation_or_validation_failed') for c in SELECTED]})


def good():
    return {'scores': {d: 2 for d in ('correctness', 'applicability', 'citation_support', 'question_completeness', 'relevance')},
            'issues': [], 'uncertainty': 'low'}


def test_parse_accepts_valid_and_wrapped_json():
    assert parse_review('Here: ' + json.dumps(good()))['uncertainty'] == 'low'


@pytest.mark.parametrize('mutate', [
    lambda d: d['scores'].pop('relevance'),
    lambda d: d['scores'].update(relevance=3),
    lambda d: d.update(issues=[{'dimension': 'relevance', 'source_ids': [], 'description': 'x'}]),
])
def test_parse_rejects_invalid_reviews(mutate):
    data = good()
    mutate(data)
    with pytest.raises(ModelError):
        parse_review(json.dumps(data))
    with pytest.raises(ModelError):
        parse_review('not json')
