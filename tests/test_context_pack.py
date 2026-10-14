import copy

import pytest

from disputelens.client import ModelError
from disputelens.context_pack import build_context, merge_evidence, render_context


FILTERS = {'corpus': 'real', 'provider': 'Stripe', 'scheme': 'Visa', 'region': 'UK'}


def evidence(text='refund proof', start=0, end=None, length=None):
    return {'passage_id': 'p', 'text': text, 'headings': ['Refund'],
            'locator': {'reference': 'https://example.org#page=2', 'pdf_page': 2},
            'evidence_character_start': start, 'evidence_character_end': end or len(text),
            'original_evidence_characters': length or len(text), 'complete_evidence': True}


def result(name, rank, pieces, previous=None, following=None):
    return {'rank': rank, 'unit': {'chunk_id': name, 'parent_chunk_id': name,
        'previous_chunk_id': previous, 'next_chunk_id': following, 'headings': ['Refund'],
        'source_sha256': 'hash', 'metadata': {'source_id': 'visa', 'title': 'Guide',
            'corpus': 'real', 'scheme': 'Visa', 'provider': None, 'status': 'snapshot'},
        'passage_ids': [e['passage_id'] for e in pieces], 'evidence': pieces}}


def test_overlap_is_deduplicated_with_exact_character_provenance():
    merged = merge_evidence([evidence('abcde', 0, 5, 8), evidence('defgh', 3, 8, 8)])
    assert merged[0]['text'] == 'abcdefgh'
    assert merged[0]['complete_evidence']
    assert merged[0]['locator']['pdf_page'] == 2
    with pytest.raises(ModelError, match='disagree'):
        merge_evidence([evidence('abcde', 0, 5, 8), evidence('XXfgh', 3, 8, 8)])


def test_adjacent_retrieved_chunks_merge_and_do_not_fetch_missing_neighbours():
    rows = [result('a', 1, [evidence()], following='b'),
            result('b', 2, [evidence()], previous='a', following='not-retrieved')]
    original = copy.deepcopy(rows)
    pack = build_context(rows, FILTERS, {}, max_words=1000)
    assert len(pack['groups']) == 1
    assert pack['included_units'] == 2
    assert len(pack['citations']) == 1
    assert pack['groups'][0]['evidence'][0]['text'] == 'refund proof'
    assert rows == original
    assert 'not-retrieved' not in pack['text']


def test_budget_omits_intact_group_without_silent_text_trimming():
    rows = [result('a', 1, [evidence('long text ' * 100)])]
    pack = build_context(rows, FILTERS, {}, max_words=10)
    assert not pack['groups'] and not pack['text']
    assert pack['omitted_groups'][0]['unit_ids'] == ['a']


def test_wrong_scope_is_rejected_before_context_construction():
    rows = [result('a', 1, [evidence()])]
    rows[0]['unit']['metadata']['scheme'] = 'Mastercard'
    with pytest.raises(ModelError, match='applicability'):
        build_context(rows, FILTERS, {})


def test_rendering_shares_source_and_section_but_keeps_each_citation():
    pieces = []
    for n in range(10):
        piece = evidence('exact evidence ' + str(n))
        piece['passage_id'] = 'p' + str(n)
        pieces.append(piece)
    rows = [result('a', 1, pieces)]
    rows[0]['unit']['metadata']['url'] = 'https://example.org'
    pack = build_context(rows, FILTERS, {}, max_words=1000)
    text = pack['text']
    assert text.count('URL: https://example.org') == 1
    assert text.count('SECTION: Refund') == 1
    assert text.count('PDF page 2; chars') == 10
    assert len(pack['citations']) == 10
    assert text == render_context(pack['groups'])
    for n, label in enumerate(pack['citations']):
        assert pack['citations'][label]['passage_id'] == 'p' + str(n)
        assert pack['citations'][label]['locator']['reference'] == 'https://example.org#page=2'
