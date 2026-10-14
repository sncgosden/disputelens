from disputelens.exception_resolver import exception_tokens, resolve, verdict

LISTED = """The issuer must ensure all of the following occurred:
–   The issuer closed the account.
–   The issuer blocked the account.
–   The issuer listed the account.
This requirement does not apply when one of the following occurred:
–   The card was issued in the Latin America and the Caribbean region.
–   The BIN was assigned for Germany."""


def passage(pid, text):
    return {'citation_id': pid, 'text': text}


def test_tokens_from_exception_items():
    assert sorted(exception_tokens(LISTED)) == ['germany', 'latin america and the caribbean']


def test_resolves_to_single_stem_from_sibling():
    sibling = passage('S2', 'Listing the PAN on the Stand-in Account File is not required when the BIN is for Germany.')
    assert resolve(passage('S1', LISTED), [passage('S1', LISTED), sibling]) == {'outcome': 'resolved', 'stem': 'list', 'by': ['S2']}


def test_ambiguous_without_sibling_and_conflicting_with_two_stems():
    assert resolve(passage('S1', LISTED), [passage('S1', LISTED)])['outcome'] == 'ambiguous'
    a = passage('S2', 'The issuer blocked the account except for Germany.')
    b = passage('S3', 'Listing the PAN is not required for Germany.')
    assert resolve(passage('S1', LISTED), [a, b])['outcome'] == 'conflicting'


def test_verdict_flags_failure():
    assert verdict({'E23:S045': {'outcome': 'ambiguous'}})['overall_pass'] is False
