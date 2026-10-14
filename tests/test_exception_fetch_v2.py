from disputelens.exception_fetch_v2 import eviction, relatedness, shared_depth, find_candidates

A = ['G', 'Ch', 'Fraud (Message Reason Codes 4837)', 'No Cardholder Authorization (Message Reason Code 4837/37)', 'No Cardholder Authorization', 'Pre-arbitration']
B = ['G', 'Ch', 'Fraud (Message Reason Codes 4837)', 'No Cardholder Authorization (Message Reason Code 4837/37)', 'No Cardholder Authorization', 'Issuer Chargeback']
C = ['G', 'Ch', 'Other section']


def test_depth_and_labels():
    assert shared_depth(A, B) == 3
    assert relatedness(A, A) == 'same step'
    assert relatedness(A, B) == 'same section, different step'
    assert relatedness(A, C) == 'unrelated'


def test_find_candidates_ranks_by_depth_and_joins_wrapped_lines():
    chunks = [{'chunk_id': 'c1', 'headings': C, 'text': 'Listing the PAN is required for Germany.'},
              {'chunk_id': 'c2', 'headings': B, 'text': 'Listing the PAN\non the file is required for Germany.'}]
    found = find_candidates(A, ['germany'], chunks)
    assert [c['chunk_id'] for c in found] == ['c2', 'c1']
    assert found[0]['sentence'] == 'Listing the PAN on the file is required for Germany.'


def test_eviction_spares_cited_and_uses_fewest_passages():
    case = {'answer': {'claims': [{'citations': [{'id': 'S1'}]}]},
            'frozen_context_pack': {'budget': {'used': 5950}, 'groups': [{'evidence': [
                {'citation_id': 'S1', 'text': 'w ' * 500}, {'citation_id': 'S2', 'text': 'w ' * 10}, {'citation_id': 'S3', 'text': 'w ' * 80}]}]}}
    r = eviction(case, 48)
    assert r['evicted'] == ['S3'] and 'S1' not in r['evicted'] and r['feasible']
