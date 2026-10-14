from disputelens.scope_gate import gate


def ev(i, h):
    return {'citation_id': i, 'headings': ['G', 'Ch', *h], 'text': 'x'}


CASE = {'case_id': 'T', 'question': 'about 4837', 'frozen_context_pack': {'groups': [{'evidence': [
    ev('S1', ['Sec (Message Reason Code 4837)', 'Participating Countries']), ev('S2', ['Sec (Message Reason Code 4837)'])]}]}}


def ans(*claims, status='answered'):
    return {'status': status, 'missing_information': [],
            'claims': [{'text': t, 'citations': [{'id': i, 'quote': 'q'}]} for t, i in claims]}


def test_unchanged_returns_same():
    a = ans(('Core', 'S2'))
    out, audit = gate(CASE, a)
    assert out is a and audit['action'] == 'unchanged'


def test_some_flagged_conditionalised_status_partial():
    out, audit = gate(CASE, ans(('Core', 'S2'), ('Program rule', 'S1')))
    assert audit['action'] == 'conditionalised' and out['status'] == 'partial'
    assert out['claims'][0]['text'] == 'Core' and out['claims'][1]['text'].startswith('Only if this applies to you (participating countries): ')
    assert len(out['missing_information']) == 1


def test_all_flagged_fails_closed_with_audit():
    out, audit = gate(CASE, ans(('Program rule', 'S1')))
    assert out['status'] == 'needs_clarification' and out['claims'] == [] and audit['withheld_claims'] == 1
    assert 'participating countries' in out['missing_information'][0]


def test_v2_wording_uses_section_titles():
    case = {'case_id': 'T', 'question': 'about 4837', 'frozen_context_pack': {'groups': [{'evidence': [
        {'citation_id': 'S1', 'headings': ['G', 'Ch', 'Sec (Message Reason Code 4837)', 'Installment Dispute-Participating Countries (Reason Code 4850)'], 'text': 'x'},
        {'citation_id': 'S2', 'headings': ['G', 'Ch', 'Sec (Message Reason Code 4837)'], 'text': 'x'}]}]}}
    out, _ = gate(case, ans(('Core', 'S2'), ('Program rule', 'S1')), version=2)
    assert out['claims'][1]['text'].startswith('Only if your dispute is Installment Dispute-Participating Countries (Reason Code 4850): ')
    out, _ = gate(case, ans(('Program rule', 'S1')), version=2)
    assert 'for example: Installment Dispute-Participating Countries (Reason Code 4850).' in out['missing_information'][0]
