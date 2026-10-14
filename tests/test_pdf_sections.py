from disputelens.pdf_sections import apply_section_headings, bookmark_sections, contains_heading


def block(page, text):
    return {'pdf_page': page, 'text': text, 'headings': ['Guide', 'running header'],
            'block_id': f'{page}:{text}'}


def test_section_hierarchy_crosses_pages_without_changing_evidence():
    blocks = [block(228, 'Previous section content'),
              block(228, 'Refund Not Processed\nThis section explains refund complaints.'),
              block(229, 'Dual Message System Chargebacks\nIssuer Chargeback'),
              block(229, 'The issuer may charge back when a refund was not processed.')]
    original = [(b['block_id'], b['text']) for b in blocks]
    events = [
        {'page': 227, 'title': 'Arbitration', 'path': ['Dual Message', 'Arbitration']},
        {'page': 228, 'title': 'Refund Not Processed', 'path': ['Dual Message', 'Refund Not Processed']},
        {'page': 229, 'title': 'Issuer Chargeback',
         'path': ['Dual Message', 'Refund Not Processed', 'Issuer Chargeback']},
    ]
    audit = apply_section_headings(blocks, events, 'Guide')
    assert blocks[0]['headings'] == ['Guide', 'Dual Message', 'Arbitration']
    assert blocks[1]['headings'][-1] == 'Refund Not Processed'
    assert blocks[3]['headings'] == ['Guide', 'Dual Message', 'Refund Not Processed', 'Issuer Chargeback']
    assert [(b['block_id'], b['text']) for b in blocks] == original
    assert not audit['unmatched_text_boundaries']


def test_nested_bookmarks_and_unmatched_boundary_are_audited():
    class Reader:
        outline = [{'/Title': 'Chapter', 'page': 0},
                   [{'/Title': 'Refunds', 'page': 1},
                    [{'/Title': 'Issuer', 'page': 2}]]]

        def get_destination_page_number(self, item):
            return item['page']

    events = bookmark_sections(Reader())
    assert events[-1]['path'] == ['Chapter', 'Refunds', 'Issuer']
    blocks = [block(2, 'Title not recognized'), block(3, 'Issuer')]
    audit = apply_section_headings(blocks, events, 'Guide')
    assert audit['unmatched_text_boundaries'] == [{'page': 2, 'title': 'Refunds'}]
    assert blocks[-1]['headings'] == ['Guide', 'Chapter', 'Refunds', 'Issuer']


def test_prose_cross_reference_is_not_a_section_boundary():
    assert not contains_heading('Refer to Refund Not Processed for details.', 'Refund Not Processed')
    assert contains_heading('  Refund Not\n  Processed\nThe issuer may...', 'Refund Not Processed')
