from disputelens.flagged_answer_trial import MARKER, score


def case(cid):
    ev = lambda i, h, t='x': {'citation_id': i, 'headings': ['G', 'Ch', 'Sec (Message Reason Code 4837)', *h], 'text': t}
    return {'case_id': cid, 'question': 'Q about 4837', 'frozen_context_pack': {'groups': [{'evidence': [
        ev('S1', ['Participating Countries']), ev('S2', ['General rule'])]}]}}


def answer(status, claims, missing=()):
    return {'status': status, 'claims': [{'text': t, 'citations': [{'id': i, 'quote': 'q'}]} for t, i in claims],
            'missing_information': list(missing)}


def test_marker():
    assert MARKER.search('Only if your country participates, do X')
    assert not MARKER.search('The issuer must list the card')


def test_unconditional_flagged_claim_fails():
    r = score(case('E13'), answer('partial', [('Do X', 'S1'), ('Core rule', 'S2')]))
    assert not r['M2'] and r['unconditional_flagged_claims'] == [1] and r['M4']


def test_conditional_flagged_and_established_kept():
    r = score(case('E13'), answer('partial', [('Only if you participate, do X', 'S1'), ('Core rule', 'S2')]))
    assert r['M2'] and r['M4']


def test_e22_clarification():
    r = score(case('E22'), answer('needs_clarification', [], ['Which reason code applies?']))
    assert r['M2'] and r['M3']
