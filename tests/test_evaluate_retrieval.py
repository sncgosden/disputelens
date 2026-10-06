import pytest

from disputelens.client import ModelError
from disputelens.evaluate_retrieval import run_cases, summarize, query_type


def test_resume_does_not_repeat_successful_cases_or_omit_zero_scores(tmp_path):
    unit = {'chunk_id': 'u', 'metadata': {'corpus': 'real', 'provider': None,
            'scheme': 'Visa', 'status': 'snapshot'}, 'passage_ids': ['p'],
            'evidence': [{'passage_id': 'p', 'evidence_character_start': 0,
                          'evidence_character_end': 10, 'original_evidence_characters': 10}]}
    cases = [{'case_id': name, 'split': 'dev', 'question': name,
              'filters': {'corpus': 'real', 'provider': None, 'scheme': 'Visa', 'region': None},
              'relevant_passage_ids': ['p']} for name in ('a', 'b')]
    calls = []
    def interrupted(question, filters):
        calls.append(question)
        if question == 'b':
            raise ModelError('connection interrupted')
        return {'results': [{'rank': 1, 'unit': unit}], 'retrieval_seconds': .1}
    with pytest.raises(ModelError):
        run_cases(cases, interrupted, [unit], tmp_path, {'fixed': True})
    resumed_calls = []
    def resume(question, filters):
        resumed_calls.append(question)
        return {'results': [], 'retrieval_seconds': .2}
    records, reused = run_cases(cases, resume, [unit], tmp_path, {'fixed': True})
    assert reused == 1 and resumed_calls == ['b']
    summary = summarize(records)
    assert summary['overall']['5']['case_count'] == 2
    assert summary['overall']['5']['metrics']['passage_recall'] == {'mean': .5, 'cases': 2}
    assert summary['incomplete_evidence_case_ids_at_5'] == ['b']


def test_holdout_cases_rejected_and_dates_are_not_reason_codes(tmp_path):
    with pytest.raises(ModelError, match='development'):
        run_cases([{'split': 'holdout'}], None, [], tmp_path, {})
    assert query_type('Visa Condition 13.1') == 'exact_code'
    assert query_type('Mastercard reason code 4853') == 'exact_code'
    assert query_type('Purchased in November 2024') == 'no_explicit_code'
