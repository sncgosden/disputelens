from disputelens.exception_fetch import find_candidates, heading_words

CHUNKS = [
    {'chunk_id': 'a', 'headings': ['Guide', 'Ch', 'No Cardholder Authorization', 'Issuer Chargeback'], 'text':
     '- Listing the PAN on the Stand-in Account File is required when the card was\nissued in the Latin America and the Caribbean region.\n- other'},
    {'chunk_id': 'b', 'headings': ['Guide', 'Ch', 'Compelling evidence'], 'text':
     'The issuer listed the account. This requirement does not apply for Germany.'},
]


def test_heading_words_drop_generic_terms():
    assert heading_words(['G', 'C', 'Issuer Chargeback', 'No Cardholder Authorization']) == {'cardholder', 'authorization'}


def test_candidate_must_be_a_requirement_statement_and_ranks_by_heading():
    out = find_candidates(['G', 'C', 'Change of Reason Code to a No Cardholder Authorization'], ['latin america and the caribbean'], CHUNKS)
    assert len(out) == 1 and out[0]['chunk_id'] == 'a' and out[0]['stem'] == 'list'
    assert out[0]['window_words'] <= 120
