from disputelens.scope_detector import evaluate, flag_case, qualifiers, unestablished

H_4850 = ['Guide', 'Chapter 2', 'Cardholder Dispute (Message Reason Code 4853/53/4850)',
          'Installment Billing Dispute-Participating Countries (Reason Code 4850)', 'Issuer chargeback']
H_4837 = ['Guide', 'Chapter 2', 'Fraud-related (Message Reason Codes 4837/37/4870)', 'No Cardholder Authorization (Message Reason Code 4837/37)']


def test_deepest_coded_heading_sets_qualifier():
    assert qualifiers(H_4850)[0] == {'4850'}
    assert qualifiers(H_4837)[0] == {'4837'}


def test_established_by_question_text():
    q = 'my acquirer cites reason code 4837'
    assert unestablished(H_4837, q) == []
    assert unestablished(H_4850, q) == ['4850', 'participating countries']


def test_general_headings_are_not_flagged():
    assert unestablished(['Guide', 'Chapter', 'Visa Allocation Flow', 'Chargeback'], 'any question') == []


def case(case_id, headings, question='no codes here', status='citation_valid_requires_review'):
    return {'case_id': case_id, 'question': question, 'saved_status': status,
            'frozen_context_pack': {'groups': [{'evidence': [{'citation_id': 'S001', 'headings': headings}]}]},
            'answer': {'claims': [{'citations': [{'id': 'S001', 'quote': 'q'}]}]}}


def test_evaluate_applies_thresholds():
    protocol = {'known_defective_passages': {'A': ['S001']}, 'controls': ['C']}
    cases = [case('A', H_4850), case('C', ['G', 'Ch', 'General']), case('B', H_4850)]
    report = evaluate(cases, {'A': 0, 'B': 2, 'C': 2}, protocol)
    assert report['verdict']['T1_known_defect_recall']['pass']
    assert report['verdict']['T2_control_false_flags']['pass']
    assert report['verdict']['T3_false_flag_rate']['value'] == '1/2'
    assert report['overall_pass']
    assert set(flag_case(cases[0])) == {'S001'}
