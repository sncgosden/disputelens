from disputelens.exception_referent import evaluate, vague_exception

LISTED = """The issuer must ensure all of the following occurred:
–   The issuer closed the account.
–   The issuer blocked the account.
–   The issuer listed the account.
This requirement does not apply when one of the following occurred:
–   The transaction was domestic."""


def test_flags_vague_exception_after_list():
    assert vague_exception(LISTED).startswith('This requirement does not apply')


def test_not_flagged_without_list_or_with_explicit_referent():
    assert vague_exception('This requirement does not apply to domestic transactions.') is None
    assert vague_exception('- one\n- two\nListing the PAN is not required when the card is German.') is None
    assert vague_exception('plain text only') is None


def case(case_id, text, status='citation_valid_requires_review'):
    return {'case_id': case_id, 'saved_status': status,
            'frozen_context_pack': {'groups': [{'evidence': [{'citation_id': 'S001', 'text': text}]}]},
            'answer': {'claims': [{'citations': [{'id': 'S001', 'quote': 'q'}]}]}}


def test_thresholds():
    protocol = {'known_defective_passages': {'A': ['S001']}, 'controls': ['C']}
    report = evaluate([case('A', LISTED), case('B', 'plain'), case('C', 'plain')], {'A': 0, 'B': 2, 'C': 2}, protocol)
    assert report['overall_pass'] and report['verdict']['T3_false_flag_rate']['value'] == '0/2'
