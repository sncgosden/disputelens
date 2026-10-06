from disputelens.chunk_documents import make_chunks


def document(blocks):
    return {'parent_id': 'test', 'source_sha256': 'hash', 'metadata': {'corpus': 'fixture'}, 'blocks': blocks}


def block(identifier, heading, text, **extra):
    return {'passage_id': identifier, 'headings': [heading], 'text': text,
            'locator': {'reference': identifier}, **extra}


def test_response_condition_and_action_remain_together_when_oversized():
    text = 'If refund is due but not processed: accept the dispute.'
    chunks = make_chunks(document([block('a', 'Refund', text)]), target_words=5)
    assert len(chunks) == 1
    assert text in chunks[0]['text']
    assert chunks[0]['exceeds_target']


def test_different_heading_rules_are_not_blended_and_source_order_survives():
    chunks = make_chunks(document([block('a', 'Delivery', 'delivery evidence'),
                                   block('b', 'Refund', 'refund evidence')]))
    assert [c['passage_ids'] for c in chunks] == [['a'], ['b']]
    assert chunks[0]['headings'] == ['Delivery']
    assert chunks[1]['headings'] == ['Refund']


def test_table_provenance_and_ids_survive_repeat_builds():
    rows = [['Condition', 'Action'], ['Not delivered', 'Accept']]
    source = document([block('a', 'Table', 'Condition | Action\nNot delivered | Accept', rows=rows)])
    first = make_chunks(source)
    assert first == make_chunks(source)
    assert first[0]['evidence'][0]['rows'] == rows
    assert first[0]['evidence'][0]['locator']['reference'] == 'a'
    assert first[0]['chunk_id'] != make_chunks(source, 250)[0]['chunk_id']


def test_neighbour_links_stop_at_document_boundaries():
    first = make_chunks(document([block('a', 'Delivery', 'delivery evidence'),
                                  block('b', 'Refund', 'refund evidence')]))
    other_doc = document([block('c', 'Other', 'separate source')])
    other_doc['parent_id'] = 'other'
    second = make_chunks(other_doc)
    assert first[0]['previous_chunk_id'] is None
    assert first[0]['next_chunk_id'] == first[1]['chunk_id']
    assert first[1]['previous_chunk_id'] == first[0]['chunk_id']
    assert first[1]['next_chunk_id'] is None
    assert second[0]['previous_chunk_id'] is None
    assert second[0]['next_chunk_id'] is None


def test_overlap_repeats_complete_blocks_without_losing_new_evidence():
    source = document([block(name, 'Policy', name + ' evidence') for name in ['a', 'b', 'c', 'd']])
    chunks = make_chunks(source, target_words=6, overlap_words=2)
    assert [c['passage_ids'] for c in chunks] == [['a', 'b'], ['b', 'c'], ['c', 'd']]
    assert all(c['word_count'] <= 6 for c in chunks)
    assert [b['text'] for b in chunks[1]['evidence']] == ['b evidence', 'c evidence']


def test_overlap_never_crosses_a_heading_boundary():
    source = document([block('a', 'Delivery', 'delivery evidence'),
                       block('b', 'Refund', 'refund evidence')])
    assert [c['passage_ids'] for c in make_chunks(source, 6, 2)] == [['a'], ['b']]
