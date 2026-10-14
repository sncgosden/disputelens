import json

from disputelens.client import ModelError
from disputelens.quote_match import strip_gaps, validate_tolerant

PACK = {'citations': {'S1': {}}, 'groups': [{'evidence': [{'citation_id': 'S1', 'passage_id': 'p', 'locator': {}, 'text': 'It may be used for a fraud- related reason within 30 days.'}]}]}


def answer(quote):
    return json.dumps({'status': 'partial', 'claims': [{'text': 'c', 'citations': [{'id': 'S1', 'quote': quote}]}], 'missing_information': ['m']})


def test_strip_gaps():
    assert strip_gaps('a fraud- related  x') == 'a fraud-related x'


def test_hyphen_gap_accepted_and_reported():
    _, used = validate_tolerant(answer('for a fraud-related reason'), PACK)
    assert used


def test_other_changes_still_rejected():
    for quote in ('for a fraud-related cause', 'within 31 days', 'for a fraud related reason'):
        try:
            validate_tolerant(answer(quote), PACK)
        except ModelError:
            continue
        raise AssertionError(quote)
