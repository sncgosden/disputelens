from disputelens.embedding_units import make_embedding_units


def source(text):
    return {'chunk_id': 'source:chunk-1', 'parent_id': 'source', 'text': text,
            'headings': ['H'], 'metadata': {'corpus': 'real'},
            'config': {'target_words': 400},
            'evidence': [{'passage_id': 'p1', 'text': text[3:],
                          'locator': {'pdf_page': 2}}]}


def test_split_retains_every_character_and_records_partial_evidence():
    text = 'H\n\n' + ('row content\n' * 40)
    chunk = source(text)
    units = make_embedding_units([chunk], [{'chunk_id': chunk['chunk_id'], 'fits': False}],
                                 list, 90, 'D: ')
    assert len(units) > 1
    assert ''.join(text[u['character_start']:u['character_end']] for u in units) == text
    assert ''.join(e['text'] for u in units for e in u['evidence']) == text[3:]
    assert all(u['embedding_tokens'] + 8 <= 90 for u in units)
    assert all(u['parent_chunk_id'] == chunk['chunk_id'] for u in units)
    assert all(e['locator']['pdf_page'] == 2 and not e['complete_evidence']
               for u in units for e in u['evidence'])
    assert units[0]['previous_chunk_id'] is None
    assert units[-1]['next_chunk_id'] is None
    assert units[0]['next_chunk_id'] == units[1]['chunk_id']


def test_fitting_chunk_is_not_split_and_full_evidence_is_marked_complete():
    chunk = source('H\n\nShort evidence.')
    units = make_embedding_units([chunk], [{'chunk_id': chunk['chunk_id'], 'fits': True,
                                           'tokens': 21}], list, 90, 'D: ')
    assert len(units) == 1
    assert units[0]['chunk_id'] == chunk['chunk_id']
    assert units[0]['text'] == chunk['text']
    assert units[0]['evidence'][0]['complete_evidence']
