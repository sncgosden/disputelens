import json

import pytest

from disputelens.client import ModelError
from disputelens.grounded_answer import build_answer_prompt, validate_answer


def pack():
    return {'text': '[S001] The merchant must provide proof of delivery.',
            'trusted_settings': {'scheme': 'Visa'},
            'citations': {'S001': {'passage_id': 'p'}},
            'groups': [{'evidence': [{'citation_id': 'S001', 'passage_id': 'p',
                         'text': 'The merchant must provide\n  proof of delivery.',
                         'locator': {'pdf_page': 2}}]}]}


def answer(label='S001', quote='proof of delivery'):
    return {'status': 'answered', 'claims': [{'text': 'Provide delivery evidence.',
              'citations': [{'id': label, 'quote': quote}]}], 'missing_information': []}


def test_citation_checks_preserve_locators_and_tolerate_layout_whitespace():
    result = validate_answer(json.dumps(answer(quote='provide proof of delivery')), pack())
    assert result['citation_checks'][0]['locator'] == {'pdf_page': 2}
    assert result['structural_citation_checks_passed']
    assert 'not automatically' in result['semantic_claim_support']


@pytest.mark.parametrize('label,quote', [('S999', 'proof of delivery'),
                                      ('S001', 'refund within 14 days')])
def test_unknown_citations_and_invented_extracts_rejected(label, quote):
    with pytest.raises(ModelError, match='Invalid grounded'):
        validate_answer(json.dumps(answer(label, quote)), pack())


def test_unsupported_answer_can_abstain_but_must_explain_missing_support():
    data = {'status': 'insufficient_evidence', 'claims': [],
            'missing_information': ['The response deadline is not established by these extracts.']}
    assert validate_answer(json.dumps(data), pack())['answer']['status'] == 'insufficient_evidence'
    data['missing_information'] = []
    with pytest.raises(ModelError):
        validate_answer(json.dumps(data), pack())


def test_uncited_claim_and_duplicate_json_keys_rejected():
    data = answer()
    data['claims'][0]['citations'] = []
    with pytest.raises(ModelError):
        validate_answer(json.dumps(data), pack())
    with pytest.raises(ModelError):
        validate_answer('{"status":"answered","status":"partial","claims":[],"missing_information":[]}', pack())


def test_prompt_has_no_expected_answer_and_empty_pack_stops():
    p = pack()
    p['expected_answer'] = 'SECRET GOLD'
    assert 'SECRET GOLD' not in build_answer_prompt('What evidence?', p)
    p['text'] = ''
    with pytest.raises(ModelError, match='No evidence'):
        build_answer_prompt('What evidence?', p)


def test_noncontiguous_quotes_and_changed_punctuation_remain_rejected():
    p = pack()
    p['groups'][0]['evidence'][0]['text'] = 'The merchant didn’t respond. Other conditions apply. The refund is due.'
    with pytest.raises(ModelError, match='source wording'):
        validate_answer(json.dumps(answer(quote="The merchant didn't respond.")), p)
    with pytest.raises(ModelError, match='source wording'):
        validate_answer(json.dumps(answer(quote='The merchant didn’t respond. The refund is due.')), p)
    assert validate_answer(json.dumps(answer(quote='The merchant didn’t respond.')), p)['structural_citation_checks_passed']


def test_long_extract_has_specific_failure_reason():
    p = pack()
    p['groups'][0]['evidence'][0]['text'] = 'word ' * 61
    with pytest.raises(ModelError, match='Claim 1: supporting extract exceeds 60 words'):
        validate_answer(json.dumps(answer(quote='word ' * 61)), p)


def test_distinct_extracts_from_same_source_allowed_within_claim():
    data = answer()
    data['claims'][0]['citations'].append({'id': 'S001', 'quote': 'The merchant must provide'})
    assert len(validate_answer(json.dumps(data), pack())['citation_checks']) == 2


def test_duplicate_source_and_same_extract_rejected():
    data = answer()
    data['claims'][0]['citations'].append({'id': 'S001', 'quote': 'proof   of delivery'})
    with pytest.raises(ModelError, match='duplicate citation and extract'):
        validate_answer(json.dumps(data), pack())
